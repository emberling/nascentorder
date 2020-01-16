#!/usr/bin/env python3
VERSION = "0.5.0pre"
DEBUG = True
import sys, traceback, configparser, random, time, os.path, operator, hashlib, re, csv, math
from copy import copy
#from string import maketrans

from mml2mfvi import mml_to_akao

_isbeyondchaos = False
HIROM = 0xC00000
defaultmode = 'bcinmpx'
CONFIG_DEFAULTS = {
        'modes': defaultmode,
        'free_rom_space': '310600-3FFFFF',
        'skip_hack_detection': 'False',
        'allow_music_repeats': 'False',
        'field_music_chance': '0',
        'brr_metadata_target_offset': 'False',
        'preserve_song_data': 'False',
        'battle_music_lookup': 'battle1, boss2, boss3, battle2, battle3, 3B, battle4, boss1',
        'battle_music_ids': '24, new, new, new',
        'boss_music_ids': 'new, 14, 33',
        'pause_current_song': 'battle1, battle2, battle3, battle4, boss1',
        'romsize': '300000, 400200',
        'monsters_loc': 'F0000, F2FFF',
        'monsters_size': '20',
        'forms_loc': 'F6200, F83FF',
        'forms_size': 'F',
        'forms_count': '240',
        'forms_aux': 'F5900, F61FF',
        'forms_aux_size': '4',
        'songcount': '53C5E',
        'brrpointers': '53C5F, 53D1B',
        'brrloops': '53D1C, 53D99',
        'brrpitch': '53D9A, 53E17',
        'brradsr': '53E18, 53E95',
        'songpointers': '53E96, 53F94',
        'instruments': '53F95, 54A34',
        'brrpointerpointer': '50222, 50228, 5022E',
        'brrlooppointer': '5041C',
        'brrpitchpointer': '5049C',
        'brradsrpointer': '504DE',
        'songpointerpointer': '50538',
        'instrumentpointer': '501E3',
        'songdata': '85C7A, 9FDFF',
        'pausesongs': '506F9, 506FD',
        'battlesongs': '2BF3B, 2BF42',
        'spritesheet': '150000',
        'spritesizea': '16A0',
        'spritesizeb': '1560',
        'portraits': '2D1D00',
        'portpals': '2D5860',
        'portptrs': '36F00',
        'charpalptrs': '2CE2B',
        'charpals': '2D6300'
        }
DEFAULT_DEFAULTS = {
        'mlast': defaultmode,
        'mode1': defaultmode + ',not set',
        'mode2': defaultmode + ',not set',
        'mode3': defaultmode + ',not set',
        'mode4': defaultmode + ',not set',
        'lastfile': 'ff6.smc'
        }
        
FLAGS = set()
spoiler = {}
f_tellmewhy = False
npcdb = {}
freespace = None
MUSIC_PATH = 'music'

# function needed to share code between BC & NaO. BC needs code here to allow pyinstaller to work in single exe mode. NaO does not use single exe mode, so no need to do anything here
def safepath(vpath):
    return vpath
    
def isfile(fn):
    return os.path.isfile(fn)
    
def dprint(msg):
    if DEBUG: print(msg)
    
def despoil(txt=""):
    global spoiler
    if 'Debug' not in spoiler: spoiler['Debug'] = []
    spoiler['Debug'].append(txt)
    
    
def byte_insert(data, position, newdata, maxlength=0, end=0):
    if isinstance(newdata, int) and abs(newdata) <= 255:
        newdata = bytes([newdata])
    while position > len(data):
        data = data + b"\x00"
    if end:
        maxlength = end - position + 1
    if maxlength and len(data) > maxlength:
        newdata = newdata[:maxlength]
    return data[:position] + newdata + data[position+len(newdata):]

    
def int_insert(data, position, newdata, length, reversed=True):
    n = int(newdata)
    l = []
    while len(l) < length:
        l.append(n & 0xFF)
        n = n >> 8
    if n: dprint("WARNING: tried to insert {} into {} bytes, truncated".format(hex(newdata), length))
    if not reversed: l.reverse()
    return byte_insert(data, position, bytes(l), length)
    
def bytes_to_int(data, reversed=True):
    # n = 0
    # for i, d in enumerate(data):
        # if reversed:
            # n = n + (ord(d) << (8 * i))
        # else:
            # n = (n << (8 * i)) + ord(d)
    # return n
    if isinstance(data, int):
        return data
    else:
        endian = "little" if reversed else "big"
        return int.from_bytes(data, endian)
    
    
def to_default(cfgname):
    print("WARNING: '{}' set incorrectly in config file, reverting to default".format(cfgname))
    return CONFIG_DEFAULTS[cfgname]
    

def printspoiler(f, seed):
    def line(txt=""):
        f.write(txt + '\n')
    separator = "--------------------"
    line("NaO SEED {} INFORMATION".format(seed) + '\n')
    line()
    handled = ['Music']
    if 'Music' in spoiler:
        line("MUSIC")
        line(separator)
        for t in spoiler['Music']:
            line(t)
        line('\n')
    handled.append('Characters')
    if 'Characters' in spoiler:
        line("CHARACTERS")
        line(separator)
        for t in spoiler['Characters']:
            line(t)
        line('\n')
    handled.append('Debug')
    if 'ROM Map' in spoiler:
        line("ROM MAP")
        line(separator)
        for t in spoiler['ROM Map']:
            line(t)
        line('\n')
    handled.append('ROM Map')
    if DEBUG and 'Debug' in spoiler:
        line()
        line("DEBUG")
        line(separator)
        for t in spoiler['Debug']:
            line(t)
        line('\n')
    for k in [sk for sk in spoiler if sk not in handled]:
        line()
        line(k)
        line(separator)
        for t in spoiler[k]:
            line(t)
        line('\n')

class TrackMetadata:
    def __init__(self, title="", album="", composer="", arranged=""):
        self.title, self.album, self.composer, self.arranged = title, album, composer, arranged
        
metadata = {}

#find an empty space in ROM for some data
def put_somewhere(romdata, newdata, desc, f_silent=False):
    global freespace, spoiler
    if freespace is None:
        init_freespace()
    success = False
    for i, (start, end) in enumerate(freespace):
        room = end-start
        if room < len(newdata):
            continue
        else:
            romdata = byte_insert(romdata, start, newdata)
            freespace[i] = (start+len(newdata), end)
            if 'ROM Map' not in spoiler: spoiler['ROM Map'] = []
            spoiler['ROM Map'].append("  0x{:x} -- {}".format(start, desc))
            success= True
            break
    if not success:
        if not silent: print("ERROR: not enough free space to insert {}\n\n".format(desc))
        assert False
    return (romdata, start, end)
            
def init_freespace():
    global freespace
    fs = CONFIG.get('General', 'free_rom_space').split()
    freespace = []
    while not freespace:
        for t in fs:
            if '-' not in t: continue
            try:
                start, end = [int(n,16) for n in t.split('-')[0:2]]
            except ValueError:
                continue
            if start >= end: continue
            freespace.append((start, end))
        if not freespace:
            to_default('free_rom_space')
            continue
        break

def free_space(start, end):
    global freespace
    if freespace is None:
        init_freespace()
    freespace.append((start, end))
    
    newfs = []
    for i, (start, end) in enumerate(sorted(freespace)):
        if newfs:
            laststart, lastend = newfs[-1][0], newfs[-1][1]
            if start <= lastend + 1:
                newfs[-1] = (laststart, end)
            else:
                newfs.append((start, end))
        else:
            newfs.append((start, end))
    freespace = newfs

def claim_space(startc, endc):
    global freespace
    if freespace is None: return
    if startc > endc: return
    newfs = []
    for i, (start, end) in enumerate(sorted(freespace)):
        if startc <= start and endc >= end:
            pass
        elif startc <= start and endc >= start:
            newstart = endc+1
            if newstart < end:
                newfs.append((newstart, end))
        elif startc <= end and endc >= end:
            newend = startc-1
            if newend > start:
                newfs.append((start, newend))
        elif startc >= start and endc <= end:
            newend = startc-1
            newstart = endc+1
            if newend > start:
                newfs.append((start, newend))
            if newstart > end:
                newfs.append((newstart, end))
        else:
            newfs.append((start, end))
    freespace = newfs
    
#expects tag/req pairs encased in longer iterables, for some reason.
#why? i have no idea, and i wrote this two days ago. *shrug*
def constraint_filter(choices, choices_idx, given, given_idx=0, eq=None):
    while len(given) < given_idx+2:
        given.append([])
    tags = given[given_idx]
    if isinstance(tags, str):
        tags = tags.split(' ')
    tags = [s.strip() for s in tags if len(s.strip())]
    constraints = given[given_idx+1]
    if isinstance(constraints, str):
        constraints = constraints.split(' ')
    constraints = [s.strip() for s in constraints if len(s.strip()) > 1]
    idtags_raw = [s[1:] for s in constraints if s[0] == "#"]
    mustbe = [s[1:] for s in constraints if s[0] == '+']
    mustnot = [s[1:] for s in constraints if s[0] == '-']
    idtags = []
    for tag in idtags_raw:
        try:
            tagid = int(tag, 16)
        except ValueError:
            print(f"invalid id tag '#{tag}'")
            continue
        idtags.append(tagid)
        
    choices = list(choices)
    for i, c in enumerate(choices):
        c = list(c)
        while len(choices[i]) < choices_idx+2:
            c.append([])
        if isinstance(c[choices_idx], str):
            c[choices_idx] = c[choices_idx].split(' ')
        c[choices_idx] = [s.strip() for s in c[choices_idx] if len(s.strip())]
        if isinstance(c[choices_idx+1], str):
            c[choices_idx+1] = c[choices_idx+1].split(' ')
        c[choices_idx+1] = [s.strip() for s in c[choices_idx+1] if len(s.strip()) > 1]
        choices[i] = c
        
    newchoices = []
    for c in choices:
        ctags = c[choices_idx]
        idtags_raw = [s[1:] for s in c[choices_idx+1] if s[0] == "#"]
        cmustbe = [s[1:] for s in c[choices_idx+1] if s[0] == '+']
        cmustnot = [s[1:] for s in c[choices_idx+1] if s[0] == '-']
        idtags = []
        for tag in idtags_raw:
            try:
                tagid = int(tag, 16)
            except ValueError:
                print(f"invalid id tag '#{tag}' in constraint set {c}")
                continue
            idtags.append(tagid)
            
        mightwork = True
        if eq is not None and eq not in idtags:
            mightwork = False
            continue
        for m in mustbe:
            if m not in ctags:
                mightwork = False
                break
        if not mightwork: continue
        for m in mustnot:
            if m in ctags:
                mightwork = False
                break
        if not mightwork: continue
        for m in cmustbe:
            if m not in tags:
                mightwork = False
                break
        if not mightwork: continue
        for m in cmustnot:
            if m in tags:
                mightwork = False
                break
        if not mightwork: continue
        newchoices.append(c)
    return newchoices
    
    
# palette utilities. all of these are "good enough" approximates.
# don't expect to translate from one to the other and back w/o lossiness
char_hues = [ 0, 15, 30, 45, 60, 75, 90, 120, 150, 165, 180, 210, 240, 270, 300, 315, 330, 360 ]
char_hues_unused = char_hues[:]

huetranstable = {
    0: [31, 0, 0],
    60: [31, 31, 0],
    120: [0, 31, 0],
    180: [0, 31, 31],
    240: [0, 0, 31],
    300: [31, 0, 31],
    }

def hue_rgb(deg):
    rgbtweentable = {0: 2, 60: -1, 120: 3, 180: -2, 240: 1, 300: -3}
    while deg >= 360: deg -= 360
    remainder = deg % 60
    color = deg - remainder
    rgb = list(huetranstable[color])
    tween = rgbtweentable[color]
    descending = False
    if tween < 0:
        descending = True
    tween = abs(tween) - 1
    remainder = int((((remainder + 1) * 32) / 60.0) - 1)
    remainder = min(31, max(0, remainder))
    if descending: remainder = 31 - remainder
    rgb[tween] = remainder
    return rgb
    
def hue_deg(rgb):
    tweens = [i for i in rgb if i not in [0,31]]
    assert len(tweens) <= 1
    transtable = {tuple(v): k for k, v in list(huetranstable.items())}
    if not tweens:
        return transtable[tuple(rgb)]
    shrunk = tuple([(31 if i == 31 else 0) for i in rgb])
    grown = tuple([(0 if i == 0 else 31) for i in rgb])
    bounds = (transtable[shrunk], transtable[grown])
    prev = min(bounds)
    next = max(bounds)
    descending = False if prev == bounds[0] else True
    if descending:
        return int(next - (((tweens[0] + 1) * 60) / 32.0) - 1)
    else:
        return int((((tweens[0] + 1) * 60) / 32.0) - 1 + prev)

def shuffle_char_hues(source_hues):
    hues = list(map(hue_rgb, source_hues))
    while True:
        tryagain = False
        random.shuffle(hues)
        for v in range(0,18,3): #check for too close colors vertically (within one palette)
            chunk = hues[v:v+3]
            for i in range(len(chunk)):
                for j in range(i+1, len(chunk)):
                    difference = [(c, d) for c, d in zip(chunk[i],chunk[j]) if c != d]
                    if len(difference) < 1: difference.append((0,0))
                    if len(difference) == 1:
                        if abs(difference[0][0] - difference[0][1]) <= 8 or chunk[i] == chunk[j]:
                            tryagain = True
                if tryagain: break
            if tryagain: break
        if tryagain: continue
        for h in range(0,3): #check for too close colors horizontally (same element on different palettes)
            chunk = hues[h:len(hues):3]
            for i in range(len(chunk)):
                for j in range(i+1, len(chunk)):
                    difference = [(c, d) for c, d in zip(chunk[i],chunk[j]) if c != d]
                    if len(difference) < 1: difference.append((0,0))
                    if len(difference) == 1 :
                        if abs(difference[0][0] - difference[0][1]) <= 8:
                            tryagain = True
                if tryagain: break
            if tryagain: break
        if tryagain: continue
        break
    return hues

def guess_hue(rgb):
    assert len(rgb) >= 3
    order = [rgb.index(min(rgb)), rgb.index(max(rgb))]
    order = [order[0], [n for n in [0,1,2] if n not in order][0], order[1]]
    color = list(rgb)
    for c in color: c -= color[order[0]]
    pct = color[order[1]] / float(color[order[2]])
    pure = [0,0,0]
    pure[order[1]] = int(31 * pct)
    pure[order[2]] = 31
    return hue_deg(pure)
    
def process_misc_fixes(data_in):
    print("** Processing misc. fixes ...")
    data = data_in
    ## TODO clean this up
    # 2E85B1 '4C' -> '4F' keep Dark World song in WoR
    # THIS IS BROKEN AND MAKES MODE7 AFTER K@N CRASH
#    loc = 0x2E85B1
#    if data[loc] == "\x4C":
#        data = byte_insert(data, loc, "\x4F")
    
    # Restore or zero out class names
    loc = 0x3007DB
    o_end = 0x30084A
    print("        Original names -> class names")
    if data[loc:loc+5] == b"\x93\x84\x91\x91\x80":
        #data = byte_insert(data, loc, "\xFF" * 0x70, end=0x30084A)
        classdata = b"\xFF" * 0x70
        classes = ["Witch", "Hunter", "Knight", "Merc", "Ruler", "Bear", "Genrl.",
                "Sage", "Artist", "Pilot", "Moogle", "Feral", "Enigma", "Beast"]
        charcfg = configparser.ConfigParser()
        charcfg.read(os.path.join("custom", "SpriteImports.txt"))
        for k, v in charcfg.items("Characters"):
            try:
                if int(k, 16) < len(classes):
                    classes[int(k,16)] = v.split(',')[0].strip()
            except:
                pass
        #for i, c in enumerate(classes):
        #    if hex(i)[2:] in charcfg:
        #        classes[i] = charcfg[hex(i)[2:].split(',')[0].strip()]
        for i, c in enumerate(classes):
            classdata = byte_insert(classdata, i*8, classes[i].translate(TO_BATTLETEXT), 6)
        data = byte_insert(data, loc, classdata, end=o_end)
    return data
    
def process_sprite_fixes(data_in):
    print("** Replacing suboptimal sprites ...")
    data = data_in
    
    # Celes fix
    o_chains = 0x17D660
    o_newchains = 0x1587C0 + 0x6A * 32
    # Also uses offsets from checksums.cfg
    
    # Celes fix
    chains = data[o_newchains:o_newchains+32*6]
    data = byte_insert(data, o_chains, chains, 32*6)
    
    # ultros, chupon
    # recolors from /scratchpad
    checksumcfg = configparser.ConfigParser()
    checksumcfg.read('checksums.cfg')
    fixes = [i[1] for i in checksumcfg.items('Sprites')]
    
    for fi in fixes:
        f = [s.strip() for s in fi.split(',')]
        if len(f) >= 4:
            offset, length = int(f[0], 16), int(f[1], 16)
            oldsprite = data[offset:offset+length]
            #print "{} {}".format(f[3], hashlib.md5(oldsprite).hexdigest())
            if hashlib.md5(oldsprite).hexdigest() == f[2]:
                try:
                    with open(os.path.join("sprites", "fixes",f[3]), 'rb') as new:
                        newsprite = new.read(length)
                        data = byte_insert(data, offset, newsprite)
                except IOError:
                    print("couldn't read file {}".format(f[3]))
                    continue
        else:
            print("WARNING: improperly formatted entry {} in checksums.cfg/sprites".format(f))
        #os.path.join("music", s.changeto + "_inst.bin"
        
    return data

def unfuck_portraits(data, f_merchant=False):
    #clean up the bizarre mess BC leaves in portrait setup
    o_portptrs = 0x036F00
    o_portraits = 0x2D1D00

    loc = o_portptrs
    pt = (list(range(0, 0x10)) + ([0xE] if f_merchant else [0x10]) + [0x11, 0] +
            ([0x10] if f_merchant else [1]) + [0x12, 0, 0, 0, 0, 0, 6])
    porttable = bytes(pt)
    for i in range(0,0x1B):
        porttable = int_insert(porttable, len(porttable), 0x320*pt[i], 2)
    data = byte_insert(data, loc, porttable, 0x4F)
    
    return data
    
    
def process_sprite_imports(data_in, charlist, rename=True, id_restrict=False):
    
    o_charnames = 0x478C0
    o_sprites = 0x150000
    l_fullsprite = 0x16A0
    o_portraits = 0x2D1D00
    o_portpals = 0x2D5860
    
    spritecfg = configparser.ConfigParser()
    spritecfg.read(os.path.join("custom", "SpriteImports.txt"))
    sizecfg = configparser.ConfigParser()
    sizecfg.read(os.path.join("tables", "spritesizes.txt"))
    allnames = {"female": set(), "neutral": set(), "male": set()}
    
    try:
        with open(os.path.join("custom", "FemaleNames.txt"), "r") as nf:
            for line in nf:
                line = "".join([s for s in line if s.isalpha()])
                if len(line) > 6: line = line[:6]
                allnames['female'].add(line)
        with open(os.path.join("custom", "NeutralNames.txt"), "r") as nf:
            for line in nf:
                line = "".join([s for s in line if s.isalpha()])
                allnames['neutral'].add(line)
        with open(os.path.join("custom", "MaleNames.txt"), "r") as nf:
            for line in nf:
                line = "".join([s for s in line if s.isalpha()])
                allnames['male'].add(line)
    except IOError:
        print("ERROR: Could not open potential list of character names\n\n\n")
        assert False
        
    class Actor:
        def __init__(self, id, desc=None, gender="any", size="full", tags="", reqs=""):
            self.id, self.desc, self.gender, self.size, self.tags, self.reqs = id, desc, gender, size, tags, reqs
            if desc is None:
                self.name = "Sprite {}".format(id)
        def __repr__(self):
            return repr(vars(self))
            
    class Sprite:
        def __init__(self, name, gender, size, file, uniqueid="", tags="", reqs=""):
            self.name, self.gender, self.size, self.file, self.uniqueid, self.tags, self.reqs = name, gender, size, file, uniqueid, tags, reqs
        def __repr__(self):
            return repr(vars(self))
    
    class SpriteType:
        def __init__(self, string):
            params = string.split()
            datamap = []
            self.size = 0
            for p in params:
                if '-' in p:
                    pq = p.split('-')
                    start = int(pq[0],16) * 0x20
                    end = (int(pq[1],16)+1) * 0x20
                else:
                    start = int(p,16) * 0x20
                    end = start + 0x20
                datamap.append((start, end))
                self.size += (end - start)
            self.map = datamap
        def __repr__(self):
            return "({} bytes: {})".format(self.size, self.map)
        
        def build(self, spritesheet):
            newsheet = b""
            for m in self.map:
                newsheet += spritesheet[m[0]:m[1]]
            return newsheet
        
    def spoil(txt):
        global spoiler
        if 'Characters' not in spoiler: spoiler['Characters'] = []
        spoiler['Characters'].append(txt)
           
    #sizedb = {
    #    "full": l_fullsprite,
    #    "nr": l_fullsprite - 320
    #    }
        
    # parse config into actorlist & spritelist
    allactors, allsprites = [], []
    for k, v in spritecfg.items("Characters"):
        line = [s.strip() for s in v.split(',')]
        while len(line) < 5: line.append([])
        allactors.append(Actor(k, *line))
    for k, v in spritecfg.items("Sprites"):
        line = [s.strip() for s in v.split(',')]
        while len(line) < 6: line.append([])
        allsprites.append(Sprite(k, *line))
    
    soffsets, sizedb, spritemap = {}, {}, {}
    for k, v in sizecfg.items("Offsets"):
        try:
            soffsets[int(k,16)] = int(v,16)
        except ValueError:
            print("WARNING: unparseable sprite offset {}:{}".format(k,v))
    for k, v in sizecfg.items("SizeTypes"):
        stype = SpriteType(v)
        sizedb[k] = stype.size
        spritemap[k] = stype
    
    data_in = unfuck_portraits(data_in)
    
    iterations = 0
    while True:
        uniqueids_used, sprites_used, initials_used = set(), set(), set()
        data = data_in
        spritepos = o_sprites
        retry = False
        spoilertxt = []
        for a in allactors: 
            id = int(a.id, 16) 
            if id not in charlist: continue
            # constraints & purge dupes
            eq = id if id_restrict else None
            if eq and eq > 13:
                eq = None
                print(f"eq {eq}")
            spriteopts = constraint_filter([(s, s.tags, s.reqs) for s in allsprites], 1, (a.tags, a.reqs), eq=eq)
            spriteopts = [s[0] for s in spriteopts if s[0].uniqueid not in uniqueids_used and s[0].name not in sprites_used]
            print(spriteopts)
            #assign gender & name
            if a.gender in ["female", "male", "neutral"]:
                spriteopts = [s for s in spriteopts if s.gender == a.gender or (s.gender == "neutral" and random.choice([True, False]))]
            if not spriteopts:
                print("no sprite options, retrying")
                retry = True
                break
            thissprite = random.choice(spriteopts)
            
            if a.gender not in ["female", "male", "neutral"]:
                a.gender = thissprite.gender if thissprite.gender in ["female", "male", "neutral"] else "neutral"
                if a.gender == "neutral":
                    a.gender = random.choice(["male"] * 9 + ["female"] * 9 + ["neutral"] * 2)
            if id <= 13:
                nameopts = set([n for n in allnames[a.gender] if n[0] not in initials_used])
                for n in allnames["neutral"]:
                    if n[0] not in initials_used and random.choice([True, False]):
                        nameopts.add(n)
                if not nameopts:
                    print("no name options, retrying")
                    retry = True
                    break
                a.name = random.choice(list(nameopts))
                initials_used.add(a.name[0])
            #check filesize (nyi, everything is full size atm)
            #print "{}: {} out of {}".format(a.desc, thissprite.name, [s.name for s in spriteopts])
            try:
                size = sizedb[a.size]
            except ValueError:
                print("WARNING: actor {} has invalid size {}. Cannot make sprite changes past this point.")
                retry = False
                break
            #read image data
            filename = os.path.join("sprites", thissprite.file + ".bin")
            try:
                with open(filename, "rb") as sf:
                    sdata = sf.read()
                if len(sdata) < size: raise IOError
            except IOError:
                print("WARNING: invalid spritesheet {}. Rerolling sprites...".format(filename))
                retry = True
                break
            filename = os.path.join("sprites", thissprite.file + "-P.bin")
            if 'pixelparty' in FLAGS or (id >= 18 and id != 20):
                pdata, ppal = None, None
            else:
                try:
                    with open(filename, "rb") as pf:
                        pdata = pf.read()
                    if len(pdata) < 0x320: raise IOError
                except IOError:
                    try:
                        filename = os.path.join("sprites", thissprite.uniqueid + "-P.bin")
                        with open(filename, "rb") as pf:
                            pdata = pf.read()
                        if len(pdata) < 0x320: raise IOError
                    except IOError:
                        pdata = None
                if pdata:
                    #filename = os.path.join("sprites", thissprite.file + "-P.pal")
                    filename = filename[:-3] + "pal"
                    try:
                        with open(filename, "rb") as pp:
                            ppal = pp.read()
                        if len(ppal) < 0x20: raise IOError
                    except IOError:
                        ppal = None
            if pdata is None: #alternate fallback mode
                try:
                    filename = os.path.join("sprites", "fixes", "fallback-portrait.bin")
                    with open(filename, "rb") as pf:
                        pdata = pf.read()
                    if len(pdata) < 0x320: raise IOError
                    filename = filename[:-3] + "pal"
                    with open(filename, "rb") as pp:
                        ppal = pp.read()
                    if len(ppal) < 0x20: raise IOError
                except IOError:
                    pdata = b"\x00"*0x320
                
            
            if a.desc == "Figaro Guard":
                rdata = spritemap['onlyride'].build(sdata)
                pdata = spritemap['onlyprone'].build(sdata)
                data = byte_insert(data, soffsets[0x40], rdata)
                data = byte_insert(data, soffsets[0x52], pdata)
                
            sdata = spritemap[a.size].build(sdata)
            
            #write
            if id <= 13 and rename:
                romname = bytes(a.name, encoding="latin-1").translate(TO_BATTLETEXT)
                while len(romname) < 6: romname = romname + b"\xFF"
                if len(romname) > 6: romname = romname[:6]
                data = byte_insert(data, o_charnames + 6*int(a.id, 16), romname, 6)
            pid = 18 if id == 20 else id
            if pid <= 18 and pdata and ppal and 'pixelparty' not in FLAGS:
                loc = o_portraits + pid * 0x320
                data = byte_insert(data, loc, pdata, 0x320)
                loc = o_portpals + pid * 0x20
                data = byte_insert(data, loc, ppal, 0x20)
            loc = soffsets[id]
            data = byte_insert(data, loc, sdata, size)
            #data = byte_insert(data, spritepos, sdata, size)
            #spritepos += size
            sprites_used.add(thissprite.name)
            if thissprite.uniqueid:
                uniqueids_used.add(thissprite.uniqueid)
            if hasattr(a, 'name'):
                spoilertxt.append("{} ({}) -> {} ({})".format(id, a.desc, a.name, thissprite.name))
            else:
                spoilertxt.append("{} ({}) ---> {}".format(id, a.desc, thissprite.name))
        if iterations >= 1000:
            print("ERROR: Couldn't generate a sprite configuration that fits the chosen constraints!")
            print("You may need to add more sprites, lower some restrictions, or remove actors from randomization\n\n\n\n")
            assert False
        if retry == False:
            break
        input("\nSomething failed. Retrying..")
    for line in spoilertxt:
        spoil(line)
    return data
    
    
def process_npcdb(data_in, f_sprites=False):
    print("** Processing NPCs ...")
    global npcdb
    
    o_npcdata = 0x41D52
    o_npcend = 0x46ABF

    npcdata = data_in[o_npcdata:o_npcend+1]
    
    def dump_npc_data():
        despoil()
        despoil("NPC GFX DATA DUMP")
        despoil("     -----     ")
        loc = 0
        usedsprites = set()
        while loc < (o_npcend - o_npcdata - 6):
            s = npcdata[loc+6]
            p = (npcdata[loc+2] & 0b00011100) >> 2
            despoil("sprite {} -> palette {}".format(hex(s), hex(p)))
            usedsprites.add((s, p))
            loc += 9
        despoil()
        despoil(" NPCs use these sprites: ---")
        despoil(repr(usedsprites))
        despoil()
    
    dump_npc_data()
    loc = 0
    while loc < (o_npcend - o_npcdata - 6):
        entry = npcdata[loc:loc+9]
        s = entry[6]
        p = (entry[2] & 0b00011100) >> 2
        if (s, p) in npcdb:
            news, newp = npcdb[(s, p)]
            newp = (newp << 2) | (entry[2] & 0b11100011)
            entry = byte_insert(entry, 2, bytes([newp]))
            entry = byte_insert(entry, 6, bytes([news]))
            npcdata = byte_insert(npcdata, loc, entry, 9)
            
        loc += 9
    
    return byte_insert(data_in, o_npcdata, npcdata, end=o_npcend)
    
def process_actor_events(data_in):
    print("** Processing events ...")
    global npcdb
    
    ## walk events and adjust relevant actor changes
    ## 
    
    o_eventstart = 0xA0000
    o_eventend = 0xCE5FF
    edata = data_in[o_eventstart:o_eventend+1]
    
    commands = {}
    commandtable = configparser.ConfigParser()
    commandtable.read(os.path.join("tables", "eventcommands.txt"))
    for k, v in commandtable.items('EventCommandLength'):
        line = [s.strip() for s in v.split(',')]
        for i, entry in enumerate(line):
            if '-' in entry:
                e = [s.strip() for s in entry.split('-')]
                thisentry = e.pop()
                line.extend([hex(n)[2:] for n in range(int(e[0], 16), int(thisentry, 16))])
            else: thisentry = entry
            try:
                commands[int(thisentry,16)] = int(k)
            except ValueError:
                commands[int(thisentry,16)] = k
    
    def cmdtype(cmd):
        if cmd in commands:
            return commands[cmd]
        return 0
    
    loc = 0
    start = 0
    actorsdefault = [29]*16
    actorsprites = copy(actorsdefault)
    while loc < len(edata):
        cmd = edata[loc]
        
        if cmd == 0x37:
            actor, graphic = edata[loc+1], edata[loc+2]
            #print("{}: assign graphic {} to actor {}".format(hex(loc), hex(graphic), hex(actor)))
            if actor < len(actorsprites):
                actorsprites[actor] = graphic
        elif cmd == 0x43:
            actor, palette = edata[loc+1], edata[loc+2]
            #print("{}: assign palette {} to actor {}".format(hex(loc), hex(palette), hex(actor)))
            if actor < len(actorsprites):
                if (actorsprites[actor], palette) in npcdb:
                    edata = int_insert(edata, loc+2, npcdb[(actorsprites[actor], palette)][1], 1)
                else:
                    dprint("note: in event {} set palette {} to actor {} using sprite {}".format(hex(start+o_eventstart), palette, actor, actorsprites[actor]))
        elif cmd == 0xFE:
#            print "end of event {} ~ {}".format(hex(start+o_eventstart), hex(loc+o_eventstart))
            start = loc + 1
            actorsprites = copy(actorsdefault)
        
        f_detail = False
        if cmdtype(cmd) == 'queue':
            if f_detail: print("{}: {} -- q{}".format(hex(loc), hex(cmd), hex(edata[loc+1])))
            loc += 1
            dest = loc + edata[loc]
            while loc < dest:
                if edata[loc] == '\xFF': break
                loc += 1
        elif cmdtype(cmd) == 'bitmap':
            if f_detail: print("{}: {} -- b{}*{}".format(hex(loc), hex(cmd), hex(edata[loc+1]), hex(edata[loc+2])))
            size = edata[loc+3]*edata[loc+4]
            loc += 4 + size            
        elif cmdtype(cmd) == 'query':
            if f_detail: print("{}: {} -- ???".format(hex(loc), hex(cmd)))
            while edata[loc+1] != '\xFE' and edata[loc+3] <= 2:
                if f_detail: print("???")
                loc += 3
        elif cmdtype(cmd) == 'switch':
            if f_detail: print("{}: {} -- s{}".format(hex(loc), hex(cmd), hex(edata[loc+1])))
            loc += 1
            loc += edata[loc] * 3
        elif cmdtype(cmd) and isinstance(cmdtype(cmd), int):
            if f_detail: print("{}: {} -- {}".format(hex(loc), hex(cmd), cmdtype(cmd)))
            loc += cmdtype(cmd)
        else:
            if f_detail: print("{}: {} ||".format(hex(loc), hex(cmd)))
        loc += 1
    
    return byte_insert(data_in, o_eventstart, edata, end=o_eventend)
    
def process_char_palettes(data_in, f_cel, f_rave):
    print("** Processing palettes ...")
    global char_hues, char_hues_unused, npcdb
    char_hues_unused = shuffle_char_hues(char_hues)
    data = data_in
    
    # palette id tables
    o_charpals = 0x2CE2B
    o_menupals = 0x18EA60
    # palette data
    o_fpaldata = 0x268000
    o_bpaldata = 0x2D6300
    # also uses offsets from sprites.cfg[EventSprites]
    # TODO instead of using list of offsets, parse events data for sprite/palette setting
    
    ## assign palettes to characters
    old_pals = list(data[o_charpals:o_charpals+22])
    twinpal = random.randint(0,5)
    char_palettes_forced = list(range(0,6)) + list(range(0,6))
    char_palettes_forced.remove(twinpal)
    char_palettes_forced.append(random.choice(list(range(0,twinpal))+list(range(twinpal+0,6))))
    while char_palettes_forced[0] == twinpal or char_palettes_forced[1] == twinpal:
        random.shuffle(char_palettes_forced)
    sprite_palettes = char_palettes_forced[:4] + [twinpal, twinpal] + char_palettes_forced[4:]
    
    # by actor
    spritecfg = configparser.ConfigParser()
    spritecfg.read('sprites.cfg')
    f_use_event_sprite_table = False
    offsets = dict(spritecfg.items('EventSprites')) if f_use_event_sprite_table else {}
    
    for c in range(0, 14):
        locs = [(o_menupals + c*18 + p) for p in [0, 4, 9, 13]] + [o_charpals + c]
        if hex(c)[2:] in offsets:
            locs.extend([int(s.strip(),16) for s in offsets[hex(c)[2:]].split(',')])
        for i, loc in enumerate(locs):
            p = sprite_palettes[c]
            if i < 4: p = (data[loc] & 0xF1) | ((sprite_palettes[c] + 2) << 1)
            data = int_insert(data, loc, p, 1)
    
    if 'moogles' in offsets:
        if offsets['moogles']:
            moogle_pals = list(range(0,6)) * 2
            random.shuffle(moogle_pals)
            for i, loc in enumerate([int(s.strip(),16) for s in offsets['moogles'].split(',')]):
                data = int_insert(data, loc, sprite_palettes[c], 1)

    #print sprite_palettes
    #print old_pals
    ## by npc (processed elsewhere)
    for c in range(0,14):
        dif = sprite_palettes[c] - old_pals[c]
        while dif < 0: dif += 6
        while dif >= 6: dif -= 6
        for p in range(0,6):
            newpal = p + dif
            while newpal >= 6: newpal -= 6
            npcdb[c, p] = (c, newpal)
    for i in range(0,6):
        npcdb[(0x41, i)] = (0x41, sprite_palettes[6]) #celes chained
    #for k in sorted(npcdb): print "k {}, v {}".format(k, npcdb[k])
    
    ## assign colors to palettes
    def components_to_color(xxx_todo_changeme):
        (red, green, blue) = xxx_todo_changeme
        return red | (green << 5) | (blue << 10)
        
    def color_to_components(color): 
        blue = (color & 0x7C00) >> 10
        green = (color & 0x03E0) >> 5
        red = color & 0x001F
        return (red, green, blue)
        
    def scalecolor(color, bot, top):
        red, green, blue = color_to_components(color)
        width = top - bot
        lightest = max(red, green, blue)
        red = int(round(width*(float(red)/float(lightest)))) + bot
        green = int(round(width*(float(green)/float(lightest)))) + bot
        blue = int(round(width*(float(blue)/float(lightest)))) + bot
        return components_to_color((red, green, blue))
        
    def hsv_approx(hue, sat, val):
        floor = (1 - (float(sat) / 100)) * 31 / 2
        ceil = 31 - floor
        new_color = list(color_to_components(scalecolor(components_to_color(tuple(hue)),
                                                            int(floor), int(ceil))))
        skewtoward = [0,0,0] if val <= 50 else [31,31,31]
        skewamount = 1 - (float(val) / 50) if val <= 50 else (float(val) / 50) - 1
        for i, c in enumerate(new_color):
            new_color[i] = int(c * (1 - skewamount) + skewtoward[i] * skewamount)
        new_color = [(c if c <= 31 else 31) for c in new_color]
        new_color = [(c if c >= 0 else 0) for c in new_color] # just in case                
        return new_color
        
    def nudge_hue(hue): #designed for 'pure' hue: one 31, one 0, one anything
        new_color = hue[:]
        if len([h for h in hue if h not in [0, 31] ]) > 0:
            new_color = [(h if h in [0,31] else h + random.randint(-2,2)) for h in hue]
        elif len([h for h in hue if h == 31]) >= 2:
            nudge_idx = random.choice([i for i, h in enumerate(hue) if h == 31])
            new_color[nudge_idx] -= random.randint(0,3)
        elif 0 in hue:
            nudge_idx = random.choice([i for i, h in enumerate(hue) if h == 0])
            new_color[nudge_idx] += random.randint(0,3)
        new_color = [(c if c <= 31 else 31) for c in new_color]
        new_color = [(c if c >= 0 else 0) for c in new_color] # just in case
        return new_color
    
    def generate_normal_palette(skintone, f_cel):
        
        def nudge_apart(dynamic, static, threshold=10):
            if static - dynamic >= 360-threshold: dynamic += 360
            if dynamic - static >= 360-threshold: static += 360
            if dynamic in range(static,static+threshold):
                dynamic = static + threshold
            elif dynamic in range(static,static-threshold):
                dynamic = static - threshold
            while dynamic >= 360:
                dynamic -= 360
            return dynamic
        
        skin_hue = guess_hue(list(skintone[0]))
        hair_hue = char_hues_unused.pop(0)
        cloth_hue_deg = nudge_apart(hue_deg(char_hues_unused.pop(0)), skin_hue)
        cloth_hue = hue_rgb(cloth_hue_deg)
        acc_hue = hue_rgb(nudge_apart(hue_deg(char_hues_unused.pop(0)), skin_hue))
        
        new_palette = [[0,0,0], [3,3,3]] + list(skintone)
        new_palette = list(map(components_to_color, new_palette)) * 4
        
        hair_sat = random.choice([random.randint(15,30), random.randint(20,50), random.randint(20,75)])
        hair_light = random.choice([random.randint(60,80), random.randint(55,90)])
        hair_dark = random.randint(int(hair_light * .5),int(hair_light * .65)) if hair_sat < 40 else \
                    random.randint(int(hair_light * .45),int(hair_light * .52))
        hair_highlight = random.randint(93,100)
        hair_shadow = random.randint(10,22)
        
        cloth_sat = random.choice([random.randint(10,50), random.randint(30,60), random.randint(10,85)])
        cloth_light = random.randint(32, max(42,hair_dark + 10))
        cloth_dark = random.randint(int(cloth_light * .6), int(cloth_light * .72))
        #print(("generating palette. level report:\n hair -- {}, {}, {}, {}\n cloth -- {}, {}".format(hair_highlight, hair_light, hair_dark, hair_shadow, cloth_light, cloth_dark)))
        while hair_light >= hair_highlight - 8:
            #print(("separating hair & highlight: hair {}   highlight {}".format(hair_light, hair_highlight)))
            hair_light -= 1
            if hair_light <= int(hair_dark / .65): break
        while hair_dark <= hair_shadow + 5:
            #print(("separating hair & shadow: hair {}   shadow {}".format(hair_dark, hair_shadow)))
            hair_shadow -= 1
            if hair_shadow <= 10: break
        while cloth_dark > hair_dark - 3:
            hair_dark += 1
        cycle, done = 0, 0
        if cloth_hue_deg >= 210 and cloth_hue_deg <= 270:
            mindelta = 8
        elif cloth_hue_deg >= 180 and cloth_hue_deg <= 300:
            mindelta = 6
        else: mindelta = 4
        while cloth_dark < hair_shadow + mindelta:
            #print(("separating cloth & shadow ({}): light {}   dark {}   shadow {}".format(cycle, cloth_light, cloth_dark, hair_shadow)))
            if cycle < 1: cycle = 1
            if cycle == 1:
                if cloth_dark < int(cloth_light * .72): cloth_dark += 1
                elif done & 0b11: break
                else: cycle = 2
            elif cycle == 2:
                if hair_shadow > 10: hair_shadow -= 1
                else: done |= 0b10
                cycle = 3
            elif cycle == 3:
                if cloth_light < hair_dark + 5: cloth_light += 1
                else: done |= 0b01
                cycle = 1
        #if cycle: print(("results: \n hair -- {}, {}, {}, {}\n cloth -- {}, {}".format(hair_highlight, hair_light, hair_dark, hair_shadow, cloth_light, cloth_dark)))
        new_palette[2] = components_to_color(hsv_approx(nudge_hue(hair_hue), random.randint(80,97), random.randint(93,98)))
        new_palette[3] = components_to_color(hsv_approx(nudge_hue(hair_hue), random.randint(10,100), hair_shadow))
        new_palette[4] = components_to_color(hsv_approx(nudge_hue(hair_hue), hair_sat + random.randint(-7,8), hair_light))
        new_palette[5] = components_to_color(hsv_approx(nudge_hue(hair_hue), hair_sat + random.randint(-7,8), hair_dark))
        new_palette[8] = components_to_color(hsv_approx(nudge_hue(cloth_hue), cloth_sat + random.randint(-7,8), cloth_light))
        new_palette[9] = components_to_color(hsv_approx(nudge_hue(cloth_hue), cloth_sat + random.randint(-7,8), cloth_dark))
        
        acc_sat = random.choice([random.randint(10,25)] + [random.randint(25,65)]*2 + [random.randint(20,85)]*2)
        acc_light = random.randint(cloth_light + 10,min(100,max(80,cloth_light + 20)))
        acc_dark = random.randint(int(acc_light * .5), int(acc_light * .68)) if acc_sat < 50 else \
                   random.randint(int(acc_light * .4), int(acc_light * .52))
        new_palette[10] = components_to_color(hsv_approx(nudge_hue(acc_hue), acc_sat + random.randint(-7,8), acc_light))
        new_palette[11] = components_to_color(hsv_approx(nudge_hue(acc_hue), acc_sat + random.randint(-7,8), acc_dark))
        
        hues = [guess_hue(hair_hue), guess_hue(cloth_hue), guess_hue(acc_hue)]
        used_range = set(range(hues[0]-15, hues[0]+15))
        used_range.update(set(range(hues[1]-15, hues[1]+15)))
        used_range.update(set(range(hues[2]-15, hues[2]+15)))
        used_range.update([n-360 for n in used_range if n > 360])
        town_hue = random.choice([n for n in range(0,360) if n not in used_range])
        town_hue = nudge_apart(town_hue, skin_hue)
        town_sat = random.choice([random.randint(10,50), random.randint(30,50), random.randint(10,65)])
        town_light = random.randint(cloth_light, hair_light)
        town_dark = random.randint(int(town_light * .6), int(town_light * .65))
        new_palette[12] = components_to_color(hsv_approx(nudge_hue(hue_rgb(town_hue)), town_sat + random.randint(-7,8), town_dark))
        new_palette[13] = components_to_color(hsv_approx(nudge_hue(hue_rgb(town_hue)), town_sat + random.randint(-7,8), town_light))
        
        used_range.update(range(town_hue-15, town_hue+15))
        aux_hue = random.choice([n for n in range(0,360) if n not in used_range])
        aux_hue = nudge_apart(aux_hue, skin_hue)
        aux_sat = random.choice([random.randint(15,30), random.randint(20,50)])
        aux_light = random.choice([random.randint(min(town_light+15,90), 100), max(40, town_light - random.randint(10,20))])
        aux_dark = random.randint(int(aux_light * .55), int(aux_light * .65))
        new_palette[14] = components_to_color(hsv_approx(nudge_hue(hue_rgb(aux_hue)), town_sat + random.randint(-7,8), aux_dark))
        new_palette[15] = components_to_color(hsv_approx(nudge_hue(hue_rgb(aux_hue)), town_sat + random.randint(-7,8), aux_light))
        
        if f_cel:
            for i in [5, 7, 9, 11]:
                new_palette[i] = new_palette[i-1]
            for i in [12, 14]:
                new_palette[i] = new_palette[i+1]
        
        return new_palette
    
    def generate_trance_palette(f_cel):
        sign = random.choice([1, -1])
        hues = [random.randint(0,360)] # skin
        if hues[0] in range(20,40): # -- discourage skin-colored skin
            hues[0] = random.randint(0,360)
        hues.append(hues[0] + random.randint(15,60) * sign) # hair
        hues.append(hues[1] + random.randint(15,60) * sign) # clothes
        hues.append(hues[2] + random.randint(15,60) * sign) # acc
        hues.append(random.randint(0,360)) #town
        hues.append(random.randint(0,360)) #aux
        
        new_palette = [[0, 0, 0], [3, 3, 3]] * 8
        
        sats, vals = [], []
        for i, h in enumerate(hues):
            while hues[i] < 0: hues[i] += 360
            while hues[i] >= 360: hues[i] -= 360
            sats.append(random.randint(80,100))
            vals.append(random.randint(80,100))
        
        new_palette[2]  = [31, 31, 31]
        new_palette[3]  = hsv_approx(nudge_hue(hue_rgb(hues[1])), sats[1], random.randint(15,30))
        new_palette[4]  = hsv_approx(nudge_hue(hue_rgb(hues[1])), sats[1], vals[1])
        new_palette[5]  = hsv_approx(nudge_hue(hue_rgb(hues[1])), sats[1], vals[1] * .66)
        new_palette[6]  = hsv_approx(nudge_hue(hue_rgb(hues[0])), sats[0], vals[0])
        new_palette[7]  = hsv_approx(nudge_hue(hue_rgb(hues[0])), sats[0], vals[0] * .66)
        new_palette[8]  = hsv_approx(nudge_hue(hue_rgb(hues[2])), sats[2], vals[2])
        new_palette[9]  = hsv_approx(nudge_hue(hue_rgb(hues[2])), sats[2], vals[2] * .66)
        new_palette[10] = hsv_approx(nudge_hue(hue_rgb(hues[3])), sats[3], vals[3])
        new_palette[11] = hsv_approx(nudge_hue(hue_rgb(hues[3])), sats[3], vals[3] * .66)
        new_palette[12] = hsv_approx(nudge_hue(hue_rgb(hues[4])), sats[4], vals[4])
        new_palette[13] = hsv_approx(nudge_hue(hue_rgb(hues[4])), sats[4], vals[4] * .66)
        new_palette[14] = hsv_approx(nudge_hue(hue_rgb(hues[5])), sats[5], vals[5])
        new_palette[15] = hsv_approx(nudge_hue(hue_rgb(hues[5])), sats[5], vals[5] * .66)
        
        if f_cel:
            for i in [5, 7, 9, 11]:
                new_palette[i] = new_palette[i-1]
            for i in [12, 14]:
                new_palette[i] = new_palette[i+1]
                
        return list(map(components_to_color, new_palette))

    skintonesraw = [v for k, v in spritecfg.items('SkinColor')]
    skintones = []
    for s in skintonesraw:
        components = [int(t.strip()) for t in s.split(',')]
        skintones.append(tuple((tuple(components[0:3]), tuple(components[3:6]))))
    
    random.shuffle(skintones)
    
    new_palettes = []
    for p in range(0,6):
        if f_rave:
            new_palettes.append(generate_trance_palette(f_cel))
        else:
            new_palettes.append(generate_normal_palette(skintones.pop(), f_cel))
    trance = generate_trance_palette(f_cel)
    
    for i, p in enumerate(new_palettes + [trance]):
        bin = b'\x00' * 32
        for j, c in enumerate(p):
            bin = int_insert(bin, j*2, c, 2)
        data = byte_insert(data, o_fpaldata + (8 if i==6 else i)*32, bin, 32)
        data = byte_insert(data, o_bpaldata + i*32, bin, 32)
    
    return data


def process_monsters(data_in):
    data = data_in
    print("** Unleashing monsters ...")
    
    o_monsters = 0x0F0000
    o_formations = 0x0F6200
    o_mgfxdata = 0x127000
    o_tileptr_s = 0x12A824
    o_tileptr_l = 0x12AC24
    o_tilebase = 0x120000
    num_monsters = 384
    num_formations = 576
    num_molds = 13
    
    formtable = configparser.ConfigParser()
    formtable.read(os.path.join("tables", "formations.txt"))
    
    ## step 1: parse monster data in ROM
    class Monster:
        def __init__(self, id):
            offset = o_monsters + id * 0x20
            m = data[offset:offset+0x20]
            self.bin = m
            self.id = id
            self.magic = True if m[0x12] & 0x01 else False
            self.humanoid = True if m[0x12] & 0x10 else False
            self.undead = True if m[0x12] & 0x80 else False
            self.rooted = True if m[0x13] & 0x04 else False
            self.flying = True if m[0x1D] & 0x01 else False
            
            self.weak, self.absorb = {}, {}
            elements = {0:"fire", 1:"ice", 2:"lightning", 3:"dark", 4:"wind", 5:"holy", 6:"earth", 7:"water"}
            for e in range(0,8):
                self.absorb[elements[e]] = True if m[0x17] & 2**e else False
                self.weak[elements[e]] = True if m[0x19] & 2**e else False
            
            self.width, self.height, self.threebit = 128, 128, False
            self.used = False
        def __repr__(self):
            st = "Monster<{:X}> -- {}x{}x{}  ".format(self.id, self.width, self.height, 8 if self.threebit else 16)
            if self.magic: st += "magic, "
            if self.humanoid: st += "humanoid, "
            if self.undead: st += "undead, "
            if self.rooted: st += "rooted, "
            if self.flying: st += "flying, "
            weak, absorb = "", ""
            for e in range(0,8):
                if self.absorb[elements[e]]: absorb += "{} & ".format(elements[e])
                if self.weak[elements[e]]: weak += "{} & ".format(elements[e])
            if weak: weak = "weak to {}, ".format(weak[0:-3])
            if absorb: absorb = "absorbs {}, ".format(absorb[0:-3])
            st += absorb + weak
            return st[0:-2]
            
    monsterdb, molds = {}, {}
    for m in range(0,num_monsters):
        monsterdb[m] = Monster(m)
    for mold_id in range(0,num_molds):
        m = [None] * 6
        line = [s.strip() for s in formtable.get("Molds", str(mold_id)).split(',')]
        for n, tok in enumerate(line):
            tok = tok.split('x')
            if len(tok) == 2:
                try:
                    w, h = int(tok[0]), int(tok[1])
                    m[n] = (w, h)
                except ValueError:
                    print("WARNING: could not parse {} in formations.txt/molds".format(tok))
            elif tok != "null":
                print("WARNING: could not parse {} in formations.txt/molds".format(tok))
        molds[mold_id] = m
    for f in range(0,num_formations):
        fd = o_formations + 15 * f
        present = fd[1]
        mold_id = fd[0] >> 4
        msb = fd[0x0E]
        for idx in range(0,6):
            mon_id = fd[idx + 2] + (256 if (msb & 2**idx) else 0)
            if present & 2**idx:
                if molds[mold_id][idx]:
                    w, h = molds[mold_id][idx]
                    monsterdb[mon_id].used = True
                    monsterdb[mon_id].width = min(monsterdb[mon_id].width, w)
                    monsterdb[mon_id].height = min(monsterdb[mon_id].height, h)
        
    ## step 2: load monster graphic candidates
    class MonsterGraphic:
        def __init__(self, metadata):
            self.name = metadata.split(":")[0].strip()
            parms = [s.strip() for s in metadata.split(":")[1].split(';')]
            params = {}
            for p in parms:
                sp = p.split(' ', 1)
                if len(sp) > 1: params[sp[0]] = sp[1]
            
            if "TAGS" in params:
                self.tags = params["TAGS"].split(' ')
            else: self.tags = []
            
            self.width = None
            if "SIZE" in params:
                sz = params["SIZE"].split('x')
                if len(sz) >= 3:
                    self.width, self.height, self.depth = sz[0], sz[1], sz[2]
                    self.tilew, self.tileh, self.bpp = int(ceil(sz[0]/8.0)), int(ceil(sz[1]/8.0)), 3 if sz[2] == 8 else 4
            if not self.width:
                self.width, self.height, self.depth = 128, 128, 16
                self.tilew, self.tileh, self.bpp = 4, 4, 4
            dim_breakpoints = [32, 64, 96]
            wclass, hclass = None, None
            for bp in dim_breakpoints:
                if not wclass and self.width < bp: wclass = bp
                if not hclass and self.height < bp: hclass = bp
            if not wclass: wclass = 128
            if not hclass: hclass = 128
            self.size_class = "{}x{}".format(wclass, hclass)
            if self.size_class == "32x96": self.size_class = "64x96"
            if self.size_class == "32x128": self.size_class = "64x128"
            if self.size_class == "64x32": self.size_class = "64x64"
            if self.size_class == "96x32": self.size_class = "96x64"
            if self.size_class in ["96x128","128x32","128x64","128x96"]: self.size_class = "128x128"
            
            if "LAYOUT" in params:
                layout = params["LAYOUT"].split(' ')
                if len(layout) != self.tileh:
                    print("WARNING: in {}: layout height {}, expected {}".format(self.name, len(layout), self.tileh))
                if len(layout) > self.tileh:
                    layout = layout[0:self.tileh]
                minw, maxw = 16,0
                for i, line in enumerate(layout):
                    if len(line) < minw: minw = len(line)
                    if len(line) > maxw:
                        maxw = len(line)
                        layout[i] = layout[i][0:self.tilew]
                    while len(line) < minw: layout[i] += "0"
                if minw < self.tilew:
                    print("WARNING: in {}: layout width {} (min), expected {}".format(self.name, minw, self.tilew))
                if maxw > self.tilew:
                    print("WARNING: in {}: layout width {} (max), expected {}".format(self.name, maxw, self.tilew))
                while len(layout) < self.tileh:
                    layout.append("0"*self.tilew)
                self.layout = layout
            else:
                self.layout = []
                while len(self.layout) < self.tileh:
                    self.layout.append("1"*self.tilew)
                
            self.palette = {}
            for n in range(0,self.depth):
                self.palette[n] = ["0"]*4
            if "PALETTE" in params:
                colors = re.findall('\w: \d+ [+-]?\d+ \d+ \d+', params["PALETTE"])
                for c in colors:
                    c = [s.strip() for s in c.split(':')]
                    try:
                        c[0] = int(c[0],16)
                    except ValueError:
                        print("WARNING: in {}: invalid palette entry {}".format(self.name, c[0]))
                        continue
                    try:
                        c[1] = [s.strip() for s in c[1].split(' ')][0:4]
                    except IndexError:
                        print("WARNING: in {}: malformed palette entry {}".format(self.name, c))
                        continue
                    self.palette[c[0]] = c[1]
                    
    try:
        with open(os.path.join("tables","enemygfx.txt"),"r") as cfgf:
            cfg = cfgf.read()
    except:
        print("ERROR: missing tables/enemygfx.txt, aborting enemy graphic changes")
        return data_in
    cfg = re.sub('#.*\n', ' ', cfg).strip()
    cfg = re.sub('\s+', ' ', cfg).strip()
    cfg = cfg.split("END;")
    graphicdb = {}
    for sprite in cfg:
        if len(sprite.split(":")) >= 2:
            name = sprite.split(":")[0].strip()
            graphicdb[name] = MonsterGraphic(sprite)
        
    ## step 3: map monsters to graphics (two passes)
    # pass 1:
    # - determine exact constraints applied to monster for graphic & palette
    # - assign graphics to monsters, reusing graphics whenever possible
    for id, monster in list(monsterdb.items()):
        if not monster.used: continue
        
    # pass 2:
    # - reassign graphics to (shuffled) monsters, favoring adding new graphics over reusing
    #   - if a graphic is found for the first time, leave it in place and note it
    #   - if a graphic is found for the second time, add a new graphic instead if there is room
    #   - if there is not room, select a valid already-added graphic randomly
    
    ## step 4: build palettes
    ## step 5: build graphic data & palette data
    ## step 6: insert layout maps & set monster graphic datas

    
def insert_instruments(data_in, metadata_pos= False):
    data = data_in
    if not _isbeyondchaos:
        print("** Inserting extended instrument samples ...")
    samplecfg = configparser.ConfigParser()
    samplecfg.read(safepath(os.path.join('tables', 'samples.txt')))
        
    #pull out instrument infos
    sampleptrs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'brrpointers').split(',')]
    if len(sampleptrs) != 2: sampleptrs = to_default('brrpointers')
    ptrdata = data[sampleptrs[0]:sampleptrs[1]+1]
    
    looplocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'brrloops').split(',')]
    if len(looplocs) != 2: looplocs = to_default('brrloops')
    loopdata = data[looplocs[0]:looplocs[1]+1]
    
    pitchlocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'brrpitch').split(',')]
    if len(pitchlocs) != 2: pitchlocs = to_default('brrpitch')
    pitchdata = data[pitchlocs[0]:pitchlocs[1]+1]
    
    adsrlocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'brradsr').split(',')]
    if len(adsrlocs) != 2: adsrlocs = to_default('brradsr')
    adsrdata = data[adsrlocs[0]:adsrlocs[1]+1]
    
    for id, smp in samplecfg.items('Samples'):
        id = int(id, 16)
        
        inst = [i.strip() for i in smp.split(',')]
        if len(inst) < 4:
            print("WARNING: malformed instrument info '{}'".format(smp))
            continue
        name, loop, pitch, adsr = inst[0:4]
        filename = name + '.brr'
        
        try:
            with open(os.path.join('samples', filename), 'rb') as f:
                sdata = f.read()
        except IOError:
            print("WARNING: couldn't load sample file {}".format(filename))
            continue
        
        try:
            loop = bytes([int(loop[0:2], 16), int(loop[2:4], 16)])
        except (ValueError, IndexError):
            print("WARNING: malformed loop info in '{}', using default".format(smp))
            loop = b"\x00\x00"
        try:
            pitch = bytes([int(pitch[0:2], 16), int(pitch[2:4], 16)])
        except (ValueError, IndexError):
            print("WARNING: malformed pitch info in '{}', using default".format(smp))
            pitch = b"\x00\x00"
        if adsr:
            try:
                attack, decay, sustain, release = [int(p,16) for p in adsr.split()[0:4]]
                assert attack < 16
                assert decay < 8
                assert sustain < 8
                assert release < 32
                ad = 1 << 7
                ad += decay << 4
                ad += attack
                sr = sustain << 5
                sr += release
                adsr = bytes([ad, sr])
            except (AssertionError, ValueError, IndexError):
                print("WARNING: malformed ADSR info in '{}', disabling envelope".format(smp))
                adsr = b"\x00\x00"
        else:
            adsr = b"\x00\x00"
            
        data, s, e = put_somewhere(data, sdata, "(sample) [{:02x}] {}".format(id, name))
        ptrdata = int_insert(ptrdata, (id-1)*3, s + HIROM, 3)
        loopdata = byte_insert(loopdata, (id-1)*2, loop, 2)
        pitchdata = byte_insert(pitchdata, (id-1)*2, pitch, 2)
        adsrdata = byte_insert(adsrdata, (id-1)*2, adsr, 2)
        
    data = byte_insert(data, sampleptrs[0], ptrdata)
    CONFIG.set('MusicPtr', 'brrpointers', "{:x}, {:x}".format(sampleptrs[0], sampleptrs[0]+len(data)))
    if metadata_pos:
        p = metadata_pos
        metadata = b"\x00"*0x600
        metadata = byte_insert(metadata, 0x0, loopdata)
        metadata = byte_insert(metadata, 0x200, pitchdata)
        metadata = byte_insert(metadata, 0x400, adsrdata)
        
        CONFIG.set('MusicPtr', 'brrloops', "{:x}, {:x}".format(0+p, 0x1FF+p))
        CONFIG.set('MusicPtr', 'brrpitch', "{:x}, {:x}".format(0x200+p, 0x3FF+p))
        CONFIG.set('MusicPtr', 'brradsr', "{:x}, {:x}".format(0x400+p, 0x5FF+p))
        
        loc = int(CONFIG.get('MusicPtr', 'brrlooppointer'),16)
        data = int_insert(data, loc, 0+p+HIROM, 3)
        loc = int(CONFIG.get('MusicPtr', 'brrpitchpointer'),16)
        data = int_insert(data, loc, 0x200+p+HIROM, 3)
        loc = int(CONFIG.get('MusicPtr', 'brradsrpointer'),16)
        data = int_insert(data, loc, 0x400+p+HIROM, 3)
        
        data = byte_insert(data, p, metadata)
    else:
        data, s, e = put_somewhere(data, loopdata, "INSTRUMENT LOOP DATA")
        CONFIG.set('MusicPtr', 'brrloops', "{:x}, {:x}".format(s, e))
        loc = int(CONFIG.get('MusicPtr', 'brrlooppointer'),16)
        data = int_insert(data, loc, s + HIROM, 3)

        data, s, e = put_somewhere(data, pitchdata, "INSTRUMENT PITCH DATA")
        CONFIG.set('MusicPtr', 'brrpitch', "{:x}, {:x}".format(s, e))
        loc = int(CONFIG.get('MusicPtr', 'brrpitchpointer'),16)
        data = int_insert(data, loc, s + HIROM, 3)

        data, s, e = put_somewhere(data, adsrdata, "INSTRUMENT ADSR DATA")
        CONFIG.set('MusicPtr', 'brradsr', "{:x}, {:x}".format(s, e))
        loc = int(CONFIG.get('MusicPtr', 'brradsrpointer'),16)
        data = int_insert(data, loc, s + HIROM, 3)
    
    return data
                

def process_custom_music(data_in, eventmodes="", opera=None, f_randomize=True, f_battleprog=True, f_mchaos=False, f_altsonglist=False):
    global freespace
    data = data_in
    freespacebackup = freespace
    f_repeat = CONFIG.getboolean('Music', 'allow_music_repeats')
    f_preserve = CONFIG.getboolean('Music', 'preserve_song_data')
    isetlocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'instruments').split(',')]
    if len(isetlocs) != 2: isetlocs = to_default('instruments')
    songdatalocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'songdata').split(',')]
    starts = songdatalocs[::2]
    ends = songdatalocs[1::2]
    if len(ends) < len(starts): ends.append(0x3FFFFF)
    songdatalocs = list(zip(starts, ends))
    native_prefix = "ff6_"
    isetsize = 0x20
    
    windy_intro = random.choice([True, False, False])
    
    def spoil(txt):
        global spoiler
        if 'Music' not in spoiler: spoiler['Music'] = []
        spoiler['Music'].append(txt)
    
    def spooler(txt):
        global spoiler, f_tellmewhy
        if f_tellmewhy:
            if 'MusicPools' not in spoiler: spoiler['MusicPools'] = []
            spoiler['MusicPools'].append(txt)
    
    def usage_id(name):
        if name.count("_") <= 1:
            return name
        return "_".join(name.split("_")[0:2])
            
    def variant_id(name, idx):
        if name.endswith("_sfx") or name.endswith("_vic"):
            name = name[:-4]
        elif name.endswith("_tr"):
            name = name[:-3]
        if idx == 0x29 or idx == 0x4F or (idx == 0x5D and windy_intro):
            #return usage_id(name) + "_sfx"
            return name + "_sfx"
        elif idx == 0x20:
            #return usage_id(name) + "_tr"
            return name + "_tr"
        elif idx == 0x2F:
            #return usage_id(name) + "_vic"
            return name + "_vic"
        else:
            return name
        
    class SongSlot:
        def __init__(self, id, chance=0, is_pointer=True, data=b"\x00\x00\x00"):
            self.id = id
            self.chance = chance
            self.choices = []
            self.changeto = ""
            self.is_pointer = is_pointer
            self.data = data
            self.inst = b""
            
    # figure out what instruments are available
    sampleptrs = [s.strip() for s in CONFIG.get('MusicPtr', 'brrpointers').split(',')]
    if len(sampleptrs) != 2: sampleptrs = to_default('brrpointers')
    instcount = (int(sampleptrs[1],16) + 1 - int(sampleptrs[0],16)) // 3
    
    ## figure out what music to use
    # build dict of original music from ROM
    try: songcountloc = int(CONFIG.get('MusicPtr', 'songcount'), 16)
    except ValueError: songcountloc = to_default('songcount')
    songptraddrs = [s.strip() for s in CONFIG.get('MusicPtr', 'songpointers').split(',')]
    if len(songptraddrs) != 2: songptraddrs = to_default('songpointers')
    songptraddrs = [int(p, 16) for p in songptraddrs]
    songptrdata = data[songptraddrs[0]:songptraddrs[1]+1]
    songptrs = []
    i = 0
    
    songcount = [data[songcountloc]]
    while i < songcount[0]:
        try: p = songptrdata[i*3:i*3+3]
        except IndexError: p = b'\x00\x00\x00'
        songptrs.append(bytes_to_int(p) - HIROM)
        i += 1
        
    # build identifier table
    songconfig = configparser.ConfigParser()
    songconfig.read(safepath(os.path.join('tables','defaultsongs.txt')))
    songconfig.read(safepath(os.path.join('custom', 'songs.txt' if not f_altsonglist else 'songs_alt.txt')))
    songtable = {}
    for ss in songconfig.items('SongSlots'):
        vals = [s.strip() for s in ss[1].split(',')]
        songtable[vals[0]] = SongSlot(int(ss[0],16), chance=int(vals[1]))
    
    tierboss = dict(songconfig.items('TierBoss'))
    
    if len(songtable) > songcount[0]:
        songcount[0] = len(songtable)
        
    # determine which songs change
    used_songs = []
    songs_to_change = []
    for ident, s in songtable.items():
        if random.randint(1, 100) > s.chance:
            if not f_repeat: used_songs.append(native_prefix + ident)
            songtable[ident].changeto = native_prefix + ident
        else:
            songs_to_change.append((ident, s))
            if f_mchaos and len(songconfig.items('Imports')) < len(songtable):
                if not songconfig.has_option('Imports', ident):
                    songconfig.set('Imports', native_prefix + ident, "")
    
    # build choice lists
    intensitytable = {}
    for song in songconfig.items('Imports'):
        canbe = [s.strip() for s in song[1].split(',')]
        intense, epic = 0, 0
        event_mults = {}
        for c in canbe:
            if not c: continue
            if c[0] in eventmodes and ":" not in c:
                try:
                    event_mults[c[0]] = int(c[1:])
                except ValueError:
                    print("WARNING: in songs.txt: could not interpret '{}'".format(c))
        static_mult = 1
        for k, v in event_mults.items():
            static_mult *= v
        if f_mchaos:
            for ident, s in songtable.items():
                s.choices.append(song[0]*static_mult)
        for c in canbe:
            if not c: continue
            if ":" in c and c[0] in eventmodes:
                c = c.split(':', 1)[1]
            if c[0] == "I":
                intense = int(c[1:])
            elif c[0] == "E" or c[0] == "G":
                epic = int(c[1:])
            elif not f_mchaos:
                if "*" in c:
                    ch = c.split('*')
                    mult = int(ch[1])
                    ch = ch[0]
                else:
                    ch = c
                    mult = 1 
                if ch in songtable:
                    songtable[ch].choices.extend([song[0]]*mult*static_mult)
        intense = max(0, min(intense, 99))
        epic = max(0, min(epic, 99))
        if (intense or epic):
            intensitytable[song[0]] = (intense, epic)
    
    for ident, s in songtable.items():
        spooler("{} pool ({}/{}): {}".format(ident, len([i for i in s.choices if i == native_prefix + ident]), len(s.choices), s.choices))
        
    # battle select
    def process_battleprog():
        newsongs = 0
        nextsongid = songcount[0]
        battleids = [s.strip() for s in CONFIG.get('Music', 'battle_music_ids').split(',')]
        bossids = [s.strip() for s in CONFIG.get('Music', 'boss_music_ids').split(',')]
        newidx = 0
        old_method = False if "battlebylevel" not in FLAGS else True
        if not old_method:
            if len(battleids) != 4 or len(bossids) != 3:
                print("WARNING: Improper song ID configuration for default method (by area)")
                print("     Falling back to old method (by level)")
                old_method = True
                FLAGS.append("battlebylevel")
                
        for i, id in enumerate(battleids):
            if str(id).lower() == "new":
                songtable['battle' + str(newidx+2)] = SongSlot(nextsongid, chance=100)
                battleids[i] = nextsongid
                nextsongid += 1
                newidx += 1
            else:
                battleids[i] = int(id, 16)
        newidx = 0
        for i, id in enumerate(bossids):
            if str(id).lower() == "new":
                songtable['EventBattle' + str(newidx)] = SongSlot(nextsongid, chance=100)
                bossids[i] = nextsongid
                nextsongid += 1
                newidx += 1
            else:
                bossids[i] = int(id, 16)
        claim_space(songptraddrs[0], songptraddrs[0] + 3*len(songtable))
        
        # what this is trying to do is:
        # we judge songs by pure INTENSITY or by combined INTENSITY and GRANDEUR
        # old method: all songs separated by pure intensity into battle and boss
        # within these categories they are set in combined rating order
        # new method: uses subsets of the I/G grid as pools for songs.
        # 1. event-battle (boss0) is chosen from I>33, G<33
        # 2. boss2 is chosen from I>min(boss0,60), G>66
        # 3. boss1 is chosen from I>boss0, boss0<G<boss2
        # 4. battle0 and battle1 chosen from I<boss0, G<max(50,boss1), sorted by G
        # 5. battle2 and battle3 chosen from I<boss2, G>battle1
        def intensity_subset(imin=0, gmin=0, imax=99, gmax=99):
            subset = {k: v for k, v in intensitytable.items() if v[0] >= imin and v[0] <= imax and v[1] >= gmin and v[1] <= gmax and usage_id(k) not in used_songs}
            return subset
            
        battlecount = len(battleids) + len(bossids)
        while len(intensitytable) < battlecount:
            dprint("WARNING: not enough battle songs marked, adding random song to pool")
            newsong = random.choice([k[0] for k in songconfig.items('Imports') if k not in intensitytable])
            intensitytable[newsong] = (random.randint(0,9), random.randint(0,9))

        if old_method:
            retry = True
            while retry:
                retry = False
                battlechoices = random.sample([(k, sum(intensitytable[k]), intensitytable[k][0]) for k in intensitytable.keys()], battlecount)
                for c in battlechoices:
                    if usage_id(battlechoices[0]) in used_songs: retry = True
            battlechoices.sort(key=operator.itemgetter(1))
            battleprog = [None]*len(battleids)
            bossprog = [None]*len(bossids)
            bosschoices = []
            battlechoices.sort(key=operator.itemgetter(2))
            for i in range(0, len(bossids)):
                bosschoices.append(battlechoices.pop(-1))
            bosschoices.sort(key=operator.itemgetter(1))
            while None in bossprog:
                bossprog[bossprog.index(None)] = bosschoices.pop(-1)
            bossprog.reverse()
            battlechoices.sort(key=operator.itemgetter(1))
            while None in battleprog:
                battleprog[battleprog.index(None)] = battlechoices.pop(0)
            battleprog = [b[0] for b in battleprog]
            bossprog = [b[0] for b in bossprog]
        else:
            tries=0
            event_g_max = 33 if not f_mchaos else random.randint(33,50)
            event_i_min = 33 if not f_mchaos else random.randint(20,33)
            boss2_g_min = 66 if not f_mchaos else random.randint(40,66)
            boss2_i_min = 60 if not f_mchaos else random.randint(40,60)
            boss1_g_min = 22 if not f_mchaos else random.randint(10,30)
            battle1_g_max = 50 if not f_mchaos else random.randint(50,70)
            battle1_g_cap = 80 if not f_mchaos else random.randint(80,95)
            while True:
                try:
                    event, (ei, eg) = random.choice(list(intensity_subset(imin=event_i_min, gmax=event_g_max).items()))
                    bt = min(ei,boss2_i_min) 

                    super, (si, sg) = random.choice(list(intensity_subset(imin=bt, gmin=boss2_g_min).items()))
                    boss, (bi, bg) = random.choice(list(intensity_subset(imin=bt, gmin=max(boss1_g_min,eg), gmax=sg).items()))
                    wt = min(battle1_g_cap,max(bg, battle1_g_max))
                    balance = random.sample(list(intensity_subset(imax=bt, gmax=wt).items()), 2)
                    if balance[0][1][0] + balance[0][1][1] > balance[1][1][0] + balance[1][1][1]:
                        boutside, (boi, bog) = balance[1]
                        binside, (bii, big) = balance[0]
                    else:
                        boutside, (boi, bog) = balance[0]
                        binside, (bii, big) = balance[1]
                    ruin = random.sample(list(intensity_subset(imax=min(bi, si), gmin=max(bog,big)).items()), 2)
                    if ruin[0][1][0] + ruin[0][1][1] > ruin[1][1][0] + ruin[1][1][1]:
                        routside, (roi, rog) = ruin[1]
                        rinside, (rii, rig) = ruin[0]
                    else:
                        routside, (roi, rog) = ruin[0]
                        rinside, (rii, rig) = ruin[1]
                    battleprog = [boutside, binside, routside, rinside]
                    bossprog = [event, boss, super]
                    if len(set(battleprog) | set(bossprog)) < 7:
                        tries += 1
                        continue
                except IndexError as e:
                    print("DEBUG: new battle prog mode failed {}rd attempt: {}".format(tries, e))
                    input("press enter to continue>")
                    if tries >= 500:
                        FLAGS.append("battlebylevel")
                        print("WARNING: couldn't find valid configuration of battle songs by area.")
                        print("     Falling back to old method (by level).")
                        return process_battleprog()
                    else:
                        tries += 1
                        continue
                break
                    
        fightids = [(id, False) for id in battleids] + [(id, True) for id in bossids]
        for id, is_boss in fightids:
            for ident, s in songtable.items():
                if s.id == id:
                    if is_boss:
                        changeto = bossprog[bossids.index(id)]
                    else:
                        changeto = battleprog[battleids.index(id)]
                    s.changeto = changeto
                    used_songs.append(usage_id(changeto))

        return (battleids, bossids)
    
    def check_ids_fit():
        n_by_isets = (isetlocs[1] - isetlocs[0] + 1) // 0x20
        n_by_sptrs = (songptraddrs[1] - songptraddrs[0] + 1) // 3
        if len(songtable) > n_by_isets or len(songtable) > n_by_sptrs:
            return False
        return True
        
    def process_mml(id, orig_mml, name):
        def wind_increment(m):
            val = int(m.group(1))
            if val in [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14]:
                val += 2
            elif val in [7, 8, 15, 16]: 
                val -= 6
            return "{{{}}}".format(val)
            return m.group(0)
            
        sfx = ""
        is_sfxv = False
        mml = orig_mml
        if id == 0x29:
            sfx = "sfx_zozo.mmlappend"
            is_sfxv = True
        elif id == 0x4F or (id == 0x5D and windy_intro):
            sfx = "sfx_wor.mmlappend"
            is_sfxv = True
            try:
                mml = re.sub("\{[^}']*?([0-9]+)[^}]*?\}", wind_increment, mml)
            except ValueError:
                print("WARNING: failed to add wind sounds ({})".format(name))
        elif id == 0x20:
            sfx = "sfx_train.mmlappend"
            mml = re.sub("\{[^}]*?([0-9]+)[^}]*?\}", "$888\g<1>", mml)
            for i in range(1,9):
                if "$888{}".format(i) not in mml:
                    mml = mml + "\n$888{} r;".format(i)
        if sfx:
            try:
                with open(os.path.join(MUSIC_PATH, sfx), 'r') as f:
                    mml += f.read()
            except IOError:
                print("couldn't open {}".format(sfx))
                
        akaov = mml_to_akao(mml, name, is_sfxv)
        if id == 0x5D and len(bytes(akaov["_default_"][0], encoding="latin-1")) > 0x1002:
            akaov = mml_to_akao(orig_mml, name, False)
        return akaov
    
    def process_tierboss(opts, used_songs=[]):
        opts_full = [o.strip() for o in opts.split(',')]
        opts = [o for o in opts_full if usage_id(o) not in used_songs]
        attempts = 0
        fallback = False
        while True:
            attempts += 1
            if attempts >= 1000:
                print("warning: check your tierboss config in songs.txt")
                fallback = True
                opts = copy(opts_full)
                attempts = 0
            retry = False
            tiernames = random.sample(opts, 3)
            tierfiles = []
            for n in tiernames:
                try:
                    with open(os.path.join(MUSIC_PATH, n + '_dm.mml'), 'r') as f:
                        tierfiles.append(f.read())
                except IOError:
                    print("couldn't open {}".format(n + '_dm.mml'))
                    retry = True
            if retry: continue
            
            mml = re.sub('[~*]', '', tierfiles[0])
            mml = re.sub('[?_]', '?', mml)
            mml = re.sub('j([0-9]+),([0-9]+)', 'j\g<1>,555\g<2>', mml)
            mml = re.sub('([;:\$])([0-9]+)(?![,0-9])', '\g<1>555\g<2>', mml)
            mml = re.sub('([;:])555444([0-9])', '\g<1>222\g<2>', mml)
            mml = re.sub('#VARIANT', '#', mml, flags=re.IGNORECASE)
            mml = re.sub('{.*?}', '', mml)
            mml = re.sub('\$555444([0-9])', '{\g<1>}', mml)
            mml = re.sub('#def\s+(\S+)\s*=', '#def 555\g<1>=', mml, flags=re.IGNORECASE)
            mml = re.sub("'(.*?)'", "'555\g<1>'", mml)
            tierfiles[0] = mml
            
            mml = re.sub('[?*]', '', tierfiles[1])
            mml = re.sub('[~_]', '?', mml)
            mml = re.sub('j([0-9]+),([0-9]+)', 'j\g<1>,666\g<2>', mml)
            mml = re.sub('([;:\$])([0-9]+)(?![,0-9])', '\g<1>666\g<2>', mml)
            mml = re.sub('([;:])666444([0-9])', '\g<1>333\g<2>', mml)
            mml = re.sub('\$666444([0-9])', '$222\g<1>', mml)
            mml = re.sub('#VARIANT', '#', mml, flags=re.IGNORECASE)
            mml = re.sub('{.*?}', '', mml)
            mml = re.sub('#def\s+(\S+)\s*=', '#def 666\g<1>=', mml, flags=re.IGNORECASE)
            mml = re.sub("'(.*?)'", "'666\g<1>'", mml)
            mml = re.sub('"', ')', mml)
            tierfiles[1] = mml
            
            mml = re.sub('[?_]', '', tierfiles[2])
            mml = re.sub('[~*]', '?', mml)
            mml = re.sub('j([0-9]+),([0-9]+)', 'j\g<1>,777\g<2>', mml)
            mml = re.sub('([;:\$])([0-9]+)(?![,0-9])', '\g<1>777\g<2>', mml)
            mml = re.sub('\$777444([0-9])', '$333\g<1>', mml)
            mml = re.sub('#VARIANT', '#', mml, flags=re.IGNORECASE)
            mml = re.sub('{.*?}', '', mml)
            mml = re.sub('#def\s+(\S+)\s*=', '#def 777\g<1>=', mml, flags=re.IGNORECASE)
            mml = re.sub("'(.*?)'", "'777\g<1>'", mml)
            mml = re.sub('"', '(', mml)
            tierfiles[2] = mml
            
            mml = "#VARIANT / \n#VARIANT ? ignore \n" + tierfiles[0] + tierfiles[1] + tierfiles[2]
            
            akao = mml_to_akao(mml, str(tiernames), variant='_default_')
            inst = bytes(akao['_default_'][1], encoding='latin-1')
            akao = bytes(akao['_default_'][0], encoding='latin-1')

            ## uncomment to debug tierboss MML
            #with open("lbdebug.mml", "w") as f:
            #    f.write(mml)
            #print("{}: {}".format(len(akao), tiernames))
            #if "name_of_segment_to_test" not in tiernames: continue
            
            if len(akao) > 0x1002:
                continue
            break
        for n in tiernames: used_songs.append(usage_id(n))
        return (akao, inst)
        
    # choose replacement songs
    used_songs_backup = used_songs
    songtable_backup = songtable
    songs_to_change_backup = songs_to_change
    keeptrying = True
    attempts = 0
    songlocations = {} #debug
    while keeptrying and attempts <= 1000:
        attempts += 1
        keeptrying = False
        data = data_in
        freespace = freespacebackup
        used_songs = copy(used_songs_backup)
        songtable = copy(songtable_backup)
        songs_to_change = copy(songs_to_change_backup)
        set_by_battleprog = []
        if f_battleprog:
            battleprog = process_battleprog()
            set_by_battleprog = battleprog[0] + battleprog[1]
        songs_to_change = [s for s in songs_to_change if s[1].id not in set_by_battleprog]
        f_moveinst = False if check_ids_fit() or f_preserve else True
        random.shuffle(songs_to_change)
        for ident, s in songs_to_change:
            if ident in tierboss:
                songtable[ident].changeto = '!!tierboss'
            else:
                choices = [c for c in songtable[ident].choices if usage_id(c) not in used_songs]
                if not choices: choices.append(native_prefix + ident)
                newsong = random.choice(choices)
                if (usage_id(newsong) in used_songs) and (not f_repeat):
                    keeptrying = True
                    break
                else:
                    if not f_repeat: used_songs.append(usage_id(newsong))
                    songtable[ident].changeto = newsong if f_randomize else native_prefix + ident
                
        if keeptrying:
            dprint("failed music generation during song selection")
            continue
        
        #get data now, so we can keeptrying if there's not enough space
        for ident, s in songtable.items():
            if s.changeto == '!!tierboss':
                s.data, s.inst = process_tierboss(tierboss[ident], used_songs=used_songs)
                s.is_pointer = False
            # case: get song from MML
            elif isfile(os.path.join(MUSIC_PATH, s.changeto + ".mml")) or isfile(os.path.join(MUSIC_PATH, usage_id(s.changeto) + ".mml")) or isfile(os.path.join(MUSIC_PATH, variant_id(s.changeto, s.id) + ".mml")):

                target = variant_id(s.changeto, s.id)
                potential_files = {}
                found = False
                while True:
                    file_to_check = target
                    variant_to_check = ""
                    while True:
                        mml, akao = "", {}
                        if file_to_check in potential_files:
                            mml, akao = potential_files[file_to_check]
                        else:
                            try:
                                with open(os.path.join(MUSIC_PATH, file_to_check + ".mml"), 'r') as mmlf:
                                    mml = mmlf.read()
                                akao = process_mml(s.id, mml, file_to_check + ".mml")
                                potential_files[file_to_check] = (mml, akao)
                            except IOError:
                                potential_files[file_to_check] = ("", {})
                        if akao and (variant_to_check in akao or variant_to_check == ""):
                            #we found it
                            variant = variant_to_check
                            found = True
                            break
                        elif file_to_check.count("_") >= 2:
                            #move a _foo_ from file to variant. if last one abort
                            file_to_check, _, variant_append = file_to_check.rpartition('_')
                            variant_to_check += variant_append + '_'
                            if variant_to_check.endswith('_'):
                                variant_to_check = variant_to_check[:-1]
                        else:
                            break
                    #stop if we found something
                    if found:
                        break
                    #we didn't find anything, so delete the last bit from target
                    elif target.count("_") >= 2:
                        target, _, _ = target.rpartition('_')
                    else:
                        #i don't think we need an actual fail case here
                        #that falls back to usage_id? should have already
                        #gotten a positive on that if available
                        mml, akao, variant = "", {}, ""
                        break
                
                #record variant - will this break stuff?
                if variant and s.changeto != target:
                    print(f"changeto != target ({s.changeto} || {target})")
                    s.changeto = f"{file_to_check} (variant: {variant})"
                    print(f"changeto changed to {s.changeto}")
                title = re.search("(?<=#TITLE )([^;\n]*)", mml, re.IGNORECASE)
                album = re.search("(?<=#ALBUM )([^;\n]*)", mml, re.IGNORECASE)
                composer = re.search("(?<=#COMPOSER )([^;\n]*)", mml, re.IGNORECASE)
                arranged = re.search("(?<=#ARRANGED )([^;\n]*)", mml, re.IGNORECASE)
                title = title.group(0) if title else "??"
                album = album.group(0) if album else "??"
                composer = composer.group(0) if composer else "??"
                arranged = arranged.group(0) if arranged else "??"
                metadata[s.changeto] = TrackMetadata(title, album, composer, arranged)
                if not akao:
                    print("couldn't find valid mml for {}".format(s.changeto))
                    keeptrying = True
                    break
                if variant and variant in akao:
                    s.data = bytes(akao[variant][0], encoding='latin-1')
                    s.inst = bytes(akao[variant][1], encoding='latin-1')
                else:
                    s.data = bytes(akao['_default_'][0], encoding='latin-1')
                    s.inst = bytes(akao['_default_'][1], encoding='latin-1')
                s.is_pointer = False
                if max(list(s.inst)) > instcount:
                    if 'nopatch' in akao:
                        s.inst = bytes(akao['nopatch'][1], encoding='latin-1')
                        s.data = bytes(akao['nopatch'][0], encoding='latin-1')
                    elif 'nat' in akao:
                        s.inst = bytes(akao['nat'][1], encoding='latin-1')
                        s.data = bytes(akao['nat'][0], encoding='latin-1')
                    else:
                        print("WARNING: instrument out of range in {}".format(s.changeto + ".mml"))
            # case: get song from source ROM
            elif not isfile(os.path.join(MUSIC_PATH, s.changeto + "_data.bin")):
                target = s.changeto[len(native_prefix):]
                if (s.changeto[:len(native_prefix)] == native_prefix and
                        target in songtable):
                    sid = songtable[target].id
                    loc = songptrs[sid]
                    assert loc >= min([l[0] for l in songdatalocs])
                    if f_preserve:
                        s.is_pointer = True
                        s.data = bytes([loc])
                    else:
                        s.is_pointer = False
                        slen = bytes_to_int(data[loc:loc+2]) + 2
                        s.data = data[loc:loc+slen]
                    loc = isetlocs[0] + sid * isetsize
                    assert loc + isetsize <= isetlocs[1] + 1
                    s.inst = data[loc:loc+isetsize]
                else:
                    keeptrying = True
                    break
            else:
                s.is_pointer = False
                # check instrument validity
                try:
                    fi = open(os.path.join(MUSIC_PATH, s.changeto + "_inst.bin"), "rb")
                    s.inst = fi.read()
                    fi.close()
                except IOError:
                    print("couldn't open {}_inst.bin".format(s.changeto))
                    keeptrying = True
                    break
                if max(list(map(ord, s.inst))) > instcount:
                    # case: get nopatch version
                    try:
                        fi = open(os.path.join(MUSIC_PATH, s.changeto + "_inst_nopatch.bin"), "rb")
                        s.inst = fi.read()
                        fi.close()
                    except IOError:
                        dprint("translating inst file for id{} {}".format(s.id, s.changeto))
                        dprint("translation is NYI")
                    try:
                        fi = open(os.path.join(MUSIC_PATH, s.changeto + "_data_nopatch.bin"), "rb")
                        s.data = fi.read()
                        fi.close()
                    except IOError:
                        try:
                            fi = open(os.path.join(MUSIC_PATH, s.changeto + "_data.bin"), "rb")
                            s.data = fi.read()
                            fi.close()
                        except IOError:
                            print("couldn't open {}_data.bin".format(s.changeto))
                            keeptrying = True
                            break
                else:
                    # case: get standard version
                    try:
                        fi = open(os.path.join(MUSIC_PATH, s.changeto + "_data.bin"), "rb")
                        s.data = fi.read()
                        fi.close()
                    except IOError:
                        print("couldn't open {}_data.bin".format(s.changeto))
                        keeptrying = True
                        break
            
            if len(s.data) > 0x1002 and "ending" not in ident:
                print("WARNING: song data too large for {} (as {}), sfx glitches may occur".format(s.changeto, ident))
                
        if keeptrying:
            dprint("failed music generation during data read")
            continue
        
        # force opera music if opera is randomized
        if opera:
            songtable['aria'].is_pointer = False
            songtable['aria'].data = bytes(opera['aria'][0], encoding='latin-1')
            songtable['aria'].inst = bytes(opera['aria'][1], encoding='latin-1')
            songtable['opera_draco'].is_pointer = False
            songtable['opera_draco'].data = bytes(opera['overture'][0], encoding='latin-1')
            songtable['opera_draco'].inst = bytes(opera['overture'][1], encoding='latin-1')
            songtable['wed_duel'].is_pointer = False
            songtable['wed_duel'].data = bytes(opera['duel'][0], encoding='latin-1')
            songtable['wed_duel'].inst = bytes(opera['duel'][1], encoding='latin-1')
            
        # try to fit it all in!
        if f_preserve:
            freelocs = []
            for b, e in songdatalocs:
                i = b
                lastchar = b''
                streak = 0
                while i <= e:
                    curchar = data[i]
                    if curchar == lastchar:
                        streak += 1
                    else:
                        if streak >= 64:
                            freelocs.append((i-(streak+1), i-1))
                        streak = 0
                    lastchar = curchar
                    i += 1
                if streak >= 64: freelocs.append((i-streak, i))
            songdatalocs = freelocs
        else:
            free_space(songdatalocs[0][0], songdatalocs[0][1])
        if f_moveinst:
            instsize = (len(songtable)+1) * 0x20
            for i, l in enumerate(songdatalocs):
                if l[1] - l[0] > instsize:
                    new_instloc = (songdatalocs[i][0], songdatalocs[i][0] + instsize - 1)
                    songdatalocs[i] = (songdatalocs[i][0] + instsize, songdatalocs[i][1])
                    break
            for i, l in enumerate(songdatalocs):
                if l[0] > l[1]: del songdatalocs[i]
        space = [e - b for b, e in songdatalocs]
        songdata = b"" * len(space)
        songinst = data[isetlocs[0]:isetlocs[1]+1]    
        if f_moveinst: free_space(isetlocs[0], isetlocs[1])
        claim_space(songptraddrs[0], songptraddrs[0] + 3*(len(songtable)+1))
        for ident, s in songtable.items():
            if not s.is_pointer:
                try:
                    data, start, end = put_somewhere(data, s.data, "  (song) [{:02x}] {}".format(s.id, s.changeto), True)
                except AssertionError:
                    data = data_in
                    continue
                songinst = byte_insert(songinst, s.id * isetsize, s.inst, isetsize)
                songptrdata = int_insert(songptrdata, s.id * 3, start + HIROM, 3)
                songlocations[s.id] = start
            else:
                songptrdata = int_insert(songptrdata, s.id * 3, s.data, 3)
                songlocations[s.id] = s.data - HIROM
                    
    if attempts >= 1000:
        print("failed to produce valid music set")
        print("    try increasing available space or adjusting song insert list")
        print("    to use less space")
        print()
        return data_in
    
    # build battle music related tables
    if f_battleprog:
        translator = {}
        battletable = [s.strip() for s in CONFIG.get('Music', 'battle_music_lookup').split(',')]
        if len(battletable) != 8: battletable = to_default('battle_music_lookup')
        pausetable = [s.strip() for s in CONFIG.get('Music', 'pause_current_song').split(',')]
        pausetableloc = int([s.strip() for s in CONFIG.get('MusicPtr', 'pausesongs').split(',')][0], 16)
        battlesongsloc = int([s.strip() for s in CONFIG.get('MusicPtr', 'battlesongs').split(',')][0], 16)
        
        for i, s in enumerate(battleprog[0]):
            translator['battle' + str(i + 1)] = s
        for i, s in enumerate(battleprog[1]):
            translator['boss' + str(i + 1)] = s
        
        def translatetbl(table):
            for i, v in enumerate(table):
                if v in translator:
                    table[i] = translator[v]
                else:
                    table[i] = int(v, 16)
        translatetbl(battletable)
        translatetbl(pausetable)
        
        battletable = bytes(battletable)
        pausetable = bytes(pausetable)
        
        
    # write to rom        
    if f_battleprog:
        data = byte_insert(data, pausetableloc, pausetable, 5)
        data = byte_insert(data, battlesongsloc, battletable, 8)
    data = int_insert(data, songcountloc, len(songtable)+1, 1)
    if not f_moveinst: songptrdata = songptrdata[:songptraddrs[1] + 1]
    data = byte_insert(data, songptraddrs[0], songptrdata)
    if f_moveinst:
        data, s, e = put_somewhere(data, songinst, "INSTRUMENT TABLES FOR SONGS")
        instlocptr = int(CONFIG.get('MusicPtr', 'instrumentpointer'), 16)
        data = int_insert(data, instlocptr, s + HIROM, 3)
    else:
        data = byte_insert(data, isetlocs[0], songinst, end=isetlocs[1])

    # make spoiler
    changed_songs = {}
    for ident, s in songtable.items():
        if s.changeto != native_prefix + ident:
            changed_songs[s.id] = (ident, s.changeto)
    spoiltext = []
    for id, s in sorted(changed_songs.items()):
        spoiltext.append(hex(id)[2:] + " : " + s[0] + " ")
    arrowpos = max(list(map(len, spoiltext)))
    for i, (id, s) in enumerate(sorted(changed_songs.items())):
        while len(spoiltext[i]) < arrowpos:
            spoiltext[i] += " "
        spoiltext[i] += "-> {}".format(s[1])
        if s[1] in metadata:
            spoiltext[i] += "\n" + " " * 8 + "{} -- {}".format(metadata[s[1]].album, metadata[s[1]].title)
            spoiltext[i] += "\n" + " " * 8 + "Composed by {} -- Arranged by {}".format(metadata[s[1]].composer, metadata[s[1]].arranged)
    for t in spoiltext: spoil(t + "\n")
    
    if DEBUG:
        fullsonglist = {}
        for ident, s in songtable.items():
            fullsonglist[s.id] = (ident, s.changeto, songlocations[s.id])
        despoil("song data locations")
        for id, (ident, newsong, loc) in fullsonglist.items():
            despoil("{} ({}) -----> {} at {}".format(hex(id), ident, newsong, hex(loc)))
    return data

    
def process_formation_music(data, f_shufflefield):
    print("** Processing progressive battle music ...")
    
    o_mpacks = 0xF4800
    o_mzones = 0xF5400
    
    formlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'forms_loc').split(',')]
    if len(formlocs) != 2: formlocs = to_default('forms_loc')
    formsize = int(CONFIG.get('EnemyPtr', 'forms_size'), 16)
    auxlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'forms_aux').split(',')]
    if len(auxlocs) != 2: auxlocs = to_default('forms_aux')
    auxsize = int(CONFIG.get('EnemyPtr', 'forms_aux_size'), 16)
    auxdata = data[auxlocs[0]:auxlocs[1]+1]
    
    # build table of monster levels
    monsterlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'monsters_loc').split(',')]
    if len(monsterlocs) != 2: monsterlocs = to_default('monsters_loc')
    monstersize = int(CONFIG.get('EnemyPtr', 'monsters_size'), 16)
    
    monstercount = (monsterlocs[1] + 1 - monsterlocs[0]) // monstersize
    monsterlevels = []
    for i in range(0, monstercount):
        levelloc = monsterlocs[0] + (i * monstersize) + 0x10
        monsterlevels.append(data[levelloc])
        
    # build table of average levels within formations
    #formcount = (formlocs[1] + 1 - formlocs[0]) / formsize
    formcount = int(CONFIG.get('EnemyPtr', 'forms_count'), 16)
    formlevels = []
    forms = [] #debug
    for i in range(0, formcount):
        loc = formlocs[0] + (i * formsize)
        flags = data[loc+1]
        form = data[loc+2:loc+8]
        levels = []
        for j in range(0,6):
            if flags & (1 << j):
                levels.append(monsterlevels[form[j]])
        if levels: 
            formlevels.append(sum(levels) // len(levels))
        else:
            formlevels.append(0)
        forms.append(list(form)) #debug

    f_bylevel = True
    if 'battlebylevel' not in FLAGS:
        f_bylevel = False
        ##### new progression, by location
        pack_map = {}
        ruin_map = set()
        try:
            with open(os.path.join('tables', 'ruinmaps.txt'), 'r') as f:
                ruin = f.read().split()
        except IOError:
            ruin = []
        for n in ruin:
            try:
                ruin_map.add(int(n, 16))
            except ValueError:
                pass        
        
        #random packs
        loc = o_mpacks
        for i in range(0,256):
            pack = []
            for j in range(0,4):
                pack.append(bytes_to_int(data[loc:loc+2]))
                loc += 2
            pack_map[i] = pack
        #event packs
        for i in range(256,512):
            pack = []
            for j in range(0,2):
                pack.append(bytes_to_int(data[loc:loc+2]))
                loc += 2
            pack_map[i] = pack
        
        form_map = {}
        form_map_d = {}
        #set wor-inside (6)
        loc = o_mzones + 512
        for i in range(0,512):
            if i in ruin_map:
                pack = pack_map[bytes_to_int(data[loc])]
                for f in pack:
                    form_map[f] = 6
                    if f in form_map_d:
                        form_map_d[f].add(6)
                    else:
                        form_map_d[f] = {6}
            loc += 1
        #set wor-outside (4)
        loc = o_mzones + 256
        for i in range(0,256):
            pack = pack_map[bytes_to_int(data[loc])]
            for f in pack:
                form_map[f] = 4
                if f in form_map_d:
                    form_map_d[f].add(4)
                else:
                    form_map_d[f] = {4}
            loc += 1
        #set event (7)
        for i in range(256,512):
            pack = pack_map[i]
            for f in pack:
                form_map[f] = 7
                if f in form_map_d:
                    form_map_d[f].add(7)
                else:
                    form_map_d[f] = {7}
        #set wob-inside (3)
        loc = o_mzones + 512
        for i in range(0,512):
            if i not in ruin_map:
                pack = pack_map[bytes_to_int(data[loc])]
                for f in pack:
                    form_map[f] = 3
                    if f in form_map_d:
                        form_map_d[f].add(3)
                    else:
                        form_map_d[f] = {3}
            loc += 1
        #set wob-outside (0)
        loc = o_mzones
        for i in range(0,256):
            if i % 4 == 3: continue #no blasted land in WoB
            pack = pack_map[bytes_to_int(data[loc])]
            for f in pack:
                form_map[f] = 0
                if f in form_map_d:
                    form_map_d[f].add(0)
                else:
                    form_map_d[f] = {0}
            loc += 1   
            
    # iterate aux form data and:
    #   if music is 1, chance to change it to 2
    #   if it's 0/3/4/6/7, set according to level percentile
    formsongs = [] #debug
    for i in range(0, formcount):
        loc = i * auxsize + 3
        byte = auxdata[loc]
        keepfield = byte >> 7
        song = (byte >> 3) & 0b111
        maxlevel = max(formlevels)
        if i in [512,513,514]:
            byte |= 0b10000000
            fanbyte = auxdata[loc-2]
            fanbyte |= 0b10
            auxdata = byte_insert(auxdata, loc-2, fanbyte)
            formsongs.append("x")
            auxdata = byte_insert(auxdata, loc, byte)
            continue
        if song == 1 and not keepfield:
            if random.randint(0, 20 + maxlevel) < (20 + formlevels[i]):
                song = 2
                byte = (byte & 0b11000111) | (song << 3)
        elif keepfield or (song not in [2, 5]):
            if f_bylevel:
                tier = maxlevel / 5
                if formlevels[i] >= tier * 4: song = 7
                elif formlevels[i] >= tier * 3: song = 6
                elif formlevels[i] >= tier * 2: song = 4
                elif formlevels[i] >= tier * 1: song = 3
                else: song = 0
            else:
                if i in form_map:
                    song = form_map[i]
                else:
                    song = 0
            byte = (byte & 0b11000111) | (song << 3)
            if f_shufflefield and (f_bylevel or song != 7):
                fieldchance = int(CONFIG.get('Music', 'field_music_chance').strip())
                if fieldchance > 100 or fieldchance < 0: fieldchance = to_default('field_music_chance')
                if  random.randint(1,100) > fieldchance:
                    byte &= 0b01111111
                    fanfare = True
                else:
                    byte |= (1 << 7)
                    fanfare = False
                fanbyte = auxdata[loc-2]
                if fanfare:
                    fanbyte &= 0b11111101
                else:
                    fanbyte |= 0b10
                auxdata = byte_insert(auxdata, loc-2, fanbyte)
        formsongs.append(song)
        auxdata = byte_insert(auxdata, loc, byte)

    if DEBUG:
        for i in range(0, monstercount):
            despoil("monster {} is level {}".format(i, monsterlevels[i]))
        for i in range(0, formcount):
            despoil()
            despoil("FORMATION {} assigned song {}".format(i, formsongs[i]))
            despoil("contains {} :: avg {}".format(forms[i], formlevels[i]))  
        
    return byte_insert(data, auxlocs[0], auxdata, end=auxlocs[1])

def process_sprite_portraits(data_in, f_merchant=False, f_changeall=False):
    print("** Processing sprite portraits ...")
    data = data_in
    
    def tile_to_pixels(tile):
        out = []
        for r in range(0,8):
            row = []
            for c in range(0,8):
                pixel = ( tile[r*2] >> (7-c) ) & 0x1
                pixel += ( (tile[r*2+1] >> (7-c) ) & 0x1 ) << 1
                pixel += ( (tile[r*2+16] >> (7-c) ) & 0x1 ) << 2
                pixel += ( (tile[r*2+17] >> (7-c) ) & 0x1 ) << 3
                row.append(pixel)
            out.append(row)
        return out
        
    def pixels_to_tile(pels):
        out = [0] * 32
        for r in range(0,8):
            for c in range(0,8):
                out[r*2] |= ( pels[r][c] & 0x1 ) << (7-c)
                out[r*2+1] |= ( ( pels[r][c] >> 1 ) & 0x1 ) << (7-c)
                out[r*2+16] |= ( ( pels[r][c] >> 2 ) & 0x1 ) << (7-c)
                out[r*2+17] |= ( ( pels[r][c] >> 3 ) & 0x1 ) << (7-c)
        return out
    
    o_spritesheet = 0x150000
    o_spritesizea = 0x16A0
    o_spritesizeb = 0x16A0 - 0x140
    o_portraits = 0x2D1D00
    o_portpals = 0x2D5860
    o_portptrs = 0x036F00
    o_charpalptrs = 0x02CE2B
    o_charpals = 0x2D6300
        
    def paint_portrait(data_in, pid):
        data = data_in
        sid = 20 if pid == 18 else pid
        if pid == 16 and f_merchant: sid = 19
        
        sloc = o_spritesheet + (min(sid,16) * o_spritesizea) + (max(0,sid-16) * o_spritesizeb)
        
        loc = sloc + 32 * 0x3E
        tiles = []
        if set(data[loc:loc+64]) == set(b"\x00"):
            loc += 64
        for t in range(0,4):
            tiles.append(data[loc:loc+32])
            loc += 32
        ptiles = []
        for t in tiles:
            ptiles.append(tile_to_pixels(t))
        
        ztiles = []
        for t in range(0,4):
            tile = []
            for r in range(0,8):
                row = []
                for c in range(0,8):
                    row.append(ptiles[t][r][c])
                    row.append(ptiles[t][r][c])
                tile.append(row)
                tile.append(row)
            ztiles.append(tile)
        
        bitmap = []
        for r in range(0,16):
            bitmap.append( [0]*4 + ztiles[0][r] + ztiles[1][r] + [0]*4 )
        for r in range(0,16):
            bitmap.append( [0]*4 + ztiles[2][r] + ztiles[3][r] + [0]*4 )
        bitmap = [ [0]*40 ] * 4 + bitmap + [ [0]*40 ] * 4
        
        btiles = []
        for tr in range(0,5):
            trow = []
            for tc in range(0,5):
                tile = []
                for r in range(0,8):
                    row = []
                    for c in range(0,8):
                        row.append(bitmap[ tr * 8 + r ][ tc * 8 + c ])
                    tile.append(row)
                trow.append(tile)
            btiles.append(trow)
        
        tlayout = [ [ 0,  1,  2,  3,  8],
                    [16, 17, 18, 19,  9],
                    [ 4,  5,  6,  7, 10],
                    [20, 21, 22, 23, 11],
                    [13, 14, 15, 24, 12] ]
        
        offset = o_portraits + pid * 0x320
        for r in range(0,5):
            for c in range(0,5):
                pos = tlayout[r][c] * 32
                loc = offset + pos
                data = byte_insert(data, loc, bytes(pixels_to_tile(btiles[r][c])))
        
        loc = o_charpalptrs + sid
        palid = data[loc]
        loc = o_charpals + palid * 32
        palette = data[loc:loc+32]
        loc = o_portpals + pid * 32
        return byte_insert(data, loc, palette, 32)
 
    ## decide whose portrait is getting changed
    ## change portrait if both:
    ## -- portrait is a known placeholder
    ## -- sprite is not an approved user of that portrait
    ## also, change portrait if two portraits are identical
    ## if known placeholder, favor first in ph cfg file, otherwise favor low chr id
    
    orig_portraits, orig_palettes = [], []
    hashcfg = configparser.ConfigParser()
    hashcfg.read("checksums.cfg")
    porthashtbl = [[j.strip() for j in i[1].split(',')] for i in hashcfg.items('Portraits')]
    porthashtbl = [h for h in porthashtbl if len(h) > 1]
    porthashes = [h[0] for h in porthashtbl]
    #print "{} placeholder hashes identified".format(len(porthashes))
    spriterecord = {}
    if f_changeall:
        changemap = [True] * 19
    else:
        changemap = [False] * 19
        for p in range(0,21):
            if p in [18, 19]: continue
            pp = 18 if p == 20 else p
            pid = data[o_portptrs + p]
            sid = p #sid = 20 if pid == 18 else pid
            loc = o_portraits + 0x320 * data[o_portptrs + p]
            thisport = data[loc:loc+0x320]
            
            thishash = hashlib.md5(thisport).hexdigest()
            #print "got portrait {} -- md5 {}".format(pid, thishash)
            if thishash in porthashes:
                spritehashes = porthashtbl[porthashes.index(thishash)][1:]
                #print "hash match (known ph). {} sprite hashes identified: {}".format(len(spritehashes), spritehashes)
                sloc = o_spritesheet + (min(sid,16) * o_spritesizea) + (max(0,sid-16) * o_spritesizeb)
                thissprite = data[sloc:sloc+o_spritesizeb]
                shash = hashlib.md5(thissprite).hexdigest()
                #print "got sprite {} -- len {} md5 {}".format(sid, len(thissprite), shash)
                if shash not in spritehashes:
                    #print "sprite not approved for placeholder. setting to change"
                    changemap[pp] = True
                else:
                    thisidx = spritehashes.index(shash)
                    if shash in spriterecord:
                        if spriterecord[shash][1] <= thisidx:
                            #print "{} found in record, supersedes idx{}".format(spriterecord[shash][1],thisidx)
                            changemap[pp] = True
                        else:
                            changemap[spriterecord[shash][0]] = False
                            spriterecord[shash] = (pid, thisidx)
                            #print "recorded {} for {}".format(spriterecord[shash], shash)
            elif thisport in orig_portraits:
                #print "this duplicates pid {}, setting to change".format(orig_portraits.index(thisport))
                changemap[pp] = True
                #print changemap
            orig_portraits.append(thisport)
            
            loc = o_portpals + pid * 32
            thispal = data[loc:loc+32]
            orig_palettes.append(thispal)

            
    for p in range(0,19):
        if changemap[p]:
            data = paint_portrait(data, p)
        else:
            loc = o_portraits + p * 0x320
            data = byte_insert(data, loc, orig_portraits[p], 0x320)
            loc = o_portpals + p * 32
            data = byte_insert(data, loc, orig_palettes[p], 32)
        
    # fix BC v64 messing up portrait pointers
    data = unfuck_portraits(data, f_merchant)
    #loc = o_portptrs
    #pt = (range(0, 0x10) + ([0xE] if f_merchant else [0x10]) + [0x11, 0] +
    #        ([0x10] if f_merchant else [1]) + [0x12, 0, 0, 0, 0, 0, 6])
    #porttable = "".join(map(chr, pt))
    #for i in xrange(0,0x1B):
    #    porttable = int_insert(porttable, len(porttable), 0x320*pt[i], 2)
    #data = byte_insert(data, loc, porttable, 0x4F)
    
    assert len(data_in) == len(data)
    return data

# tool to help exploratory design on a far future mode
# not for public but if you find this and want to try it, knock yrself out
FXDB = set()
def mangle_magic(data_in):
    data = data_in
    
    #             [sprite] [ bg1 ] [ bg3 ] [palettes ] sfx ini [esper] spd
    sanim_base = b"\x7E\x02\xFF\xFF\xFF\xFF\x9D\x9D\x9D\x16\x1B\xFF\xFF\x10"
    spell_base = b"\x21\x00\x28\x09\x21\x05\x0A\x00\x00\xFF\x00\x00\x00\x00"
    
    animtable = configparser.ConfigParser()
    animtable.read('sdev')
    
    def read_fxdb():
        global FXDB
        
        def decomment(file):
            for row in file:
                rw = row.split('#')[0].strip()
                print("{} {}".format(len(rw), rw))
                if len([c for c in rw if c == ',']) >= 10:
                    yield rw
                else:
                    print("warning: too few parameters in line: {}".format(rw))
                
        with open(os.path.join("tables", "SpellEffects.txt"), "r") as f:
            f = csv.reader(decomment(f))
            
            class SpellFx:
                def __init__(self, line):
                    self.id, self.name, self.role, self.layer, self.script, self.targets, self.palettes, self.colors, self.sounds, self.tags, self.reqs = line
                    self.id = int(self.id, 16)
                    self.script = [s.strip() for s in self.script if len(s) and s != "*"]
                    self.sounds = [s.strip() for s in self.sounds if len(s) and s != "*"]
                    self.tags = [s.strip() for s in self.tags.split(' ') if len(s.strip())]
                    #self.reqs = [s.strip() for s in self.reqs.split(' ')]
                def __repr__(self): return repr(vars(self))
            for l in f:
                FXDB.add(SpellFx(l))
    
    def parse_constraints(constraints, mustbe=None, mustnot=None):
        if mustbe is None: mustbe = set()
        if mustnot is None: mustnot = set()
        if constraints.strip():
            constraints = [s.strip() for s in constraints.split(' ') if len(s.strip())]
            mustbe.update((s[1:] for s in constraints if s[0] == '+'))
            mustnot.update((s[1:] for s in constraints if s[0] == '-'))
        if '' in mustbe: mustbe.remove('')
        if '' in mustnot: mustnot.remove('')
        return mustbe, mustnot
        
    def generate_anim(constraints):
        global FXDB
        if not FXDB: read_fxdb()
        
        class SpellAnimSub:
            def __init__(self, id, pal):
                self.id, self.pal = id, pal
            def __repr__(self): return "<ID {}, palette {}>".format(hex(self.id), hex(self.pal))
        class SpellAnim:
            def __init__(self, spr, bg1, bg3, ext, sound, script, spd, name):
                self.spr, self.bg1, self.bg3, self.ext, self.sound, self.script, self.spd, self.name = spr, bg1, bg3, ext, sound, script, spd, name
            def __repr__(self): return "-={}=-\n  sound {}, script {}, speed {}\n  Sprite {}\n  BG1    {}\n  BG3    {}\n  Extra  {}".format(self.name, self.sound, self.script, self.spd, self.spr, self.bg1, self.bg3, self.ext)
            def encode(self):
                bytestring = chr(self.spr.id & 0xFF) + chr(self.spr.id >> 8)
                bytestring += chr(self.bg1.id & 0xFF) + chr(self.bg1.id >> 8)
                bytestring += chr(self.bg3.id & 0xFF) + chr(self.bg3.id >> 8)
                bytestring += chr(self.spr.pal) + chr(self.bg1.pal) + chr(self.bg3.pal)
                bytestring += chr(self.sound) + chr(self.script)
                bytestring += chr(self.ext.id & 0xFF) + chr(self.ext.id >> 8)
                bytestring += chr(self.spd)
                return bytestring
                
        blanksub = SpellAnimSub(0xFFFF, 0)
        blankanim = SpellAnim(blanksub, blanksub, blanksub, blanksub, 0, 0x1B, 16, "       ")
        found = False
        while not found:
            aout = SpellAnim(blanksub, blanksub, blanksub, blanksub, 0, 0x1B, 16, "       ")
            failed = False
            usedlayers = ""
            mustbe, mustnot = parse_constraints(constraints)
            isalready = set()
            count = random.choice([1] + [2]*12 + [3]*66 + [4])
            anims = []
            role = "core"
            #print "creating animation with {} elements".format(count)
            
            while len(anims) < count:
                #print " filling role {}".format(role)
                #print " our spell must include tags {}".format(mustbe)
                if count - len(anims) == 1:
                    thismustbe = mustbe
                else:
                    thismustbe = set([c for c in mustbe if random.randint(0,1) and c not in isalready])
                #print " this element must be {}".format(thismustbe)
                opts = [fx for fx in FXDB if role in fx.role]
                #print " found {} options matching role".format(len(opts))
                for l in usedlayers.strip(): opts = [fx for fx in opts if l not in fx.layer]
                #print " found {} options in unused layers".format(len(opts))
                for c in thismustbe:
                    #print "looking for tag {} among options {}".format(c, [fx.tags for fx in opts])
                    opts = [fx for fx in opts if c in fx.tags]
                #print " found {} options fitting mustbe constraints {}".format(len(opts), thismustbe)
                for c in mustnot:
                    opts = [fx for fx in opts if c not in fx.tags]
                #print " found {} options fitting mustnot constraints {}".format(len(opts), mustnot)
                newopts = []
                for o in opts:
                    accept = True
                    for c in parse_constraints(o.reqs)[1]:
                        if c in isalready:
                            accept = False
                    if accept: newopts.append(o)
                opts = newopts
                #print " found {} options without conflicting mustnot constraints (already {})".format(len(opts), isalready)
                if not opts:
                    failed = True
                    #print " no options, restarting"
                    break
                    
                anims.append(random.choice(opts))
                #print " chose {}".format(anims[-1])
                if 's' in anims[-1].layer:
                    aout.spr = SpellAnimSub(anims[-1].id, 0x9D)
                if '1' in anims[-1].layer:
                    aout.bg1 = SpellAnimSub(anims[-1].id, 0x9D)
                if '3' in anims[-1].layer:
                    aout.bg3 = SpellAnimSub(anims[-1].id, 0x9D)
                if 'e' in anims[-1].layer:
                    aout.ext = SpellAnimSub(anims[-1].id, 0x9D)
                usedlayers += anims[-1].layer
                isalready.update(anims[-1].tags)
                #print " layers used: {}\n tags applied: {}".format(usedlayers, isalready)
                if role == "core":
                    aout.name = byte_insert(aout.name, 0, anims[-1].name.strip(), end=3)
                    role = "aux"
                else:
                    aout.name = byte_insert(aout.name, 4, anims[-1].name.strip(), end=6)
                #print "adding constraints {} to existing +({}) -({})".format(anims[-1].reqs, mustbe, mustnot)
                mustbe, mustnot = parse_constraints(anims[-1].reqs, mustbe, mustnot)
                #print "new constraints are +({}) -({})".format(mustbe, mustnot)
            if failed: continue
            for c in mustbe:
                if c not in isalready:
                    #print " failed to meet constraints, restarting"
                    continue
            found = True
        return aout
    
    f_random = True
    if f_random:
        # generate random spellsets for testing the algorithm
        sanims, snames, spells = "", "", ""        
        for i in range(0,20):
            a = generate_anim("")
            print(repr(a))
            spells += spell_base
            snames += a.name.translate(TO_BATTLETEXT)
            sanims += a.encode()
            
    else:
        # generate predictable spellsets for testing effects
        layertbl = {}
        for lyr in ['1', '2', '3', '4']:
            print(lyr)
            for i, d in enumerate(animtable.get('sdev', lyr).split()):
                print("{}: {} {}".format(i, type(d), d))
            for id in animtable.get('sdev', lyr).split():
                iid = int(id, 16)
                if iid not in layertbl: layertbl[iid] = []
                layertbl[iid].append(int(lyr))
        
        sanims, snames, spells = "", "", ""
        for id in sorted(layertbl.keys()):
            sid = id - 0x79
            if sid < 0: continue
            sanim = sanim_base
            namel = ""
            for lyr in [(1,0,'S'), (2,2,'1'), (3,4,'3'), (4,11,'E')]:
                f_high = False if lyr[0] == 1 else False
                if lyr[0] in layertbl[id]:
                    sanim = int_insert(sanim, lyr[1], id + f_high, 2)
                    namel += lyr[2]
                else:
                    namel += "-"
                    
            sname = "{} {}  ".format(hex(id)[2:].rjust(3,' '), namel)
            if sid <= 64: sname = sname[1:3] + sname[4:9]
            elif sid <= (64+35): sname = sname[:8]
            sanims += sanim
            snames += sname.translate(TO_BATTLETEXT)
            spells += spell_base
    
    data = byte_insert(data, 0x107FB2, sanims, end=0x1097FF)
    data = byte_insert(data, 0x26F567, snames, end=0x26FE8E)
    data = byte_insert(data, 0x046AC0, spells, end=0x0478BF)
    return data
    
def validate_custom_music(data):
    o_start = 0x53F95
    o_end = 0x9FDFF
    expected_sum = "cb137e71473d24ecfc5ff7030089793d"
    
    seg = data[o_start:o_end]
    sum = hashlib.md5(seg).hexdigest()
    if sum == expected_sum:
        return True
    else:
        print("WARNING: The selected ROM does not appear to contain the unaltered, original FF6 music. The music randomizer depends on this to function. If you wish to attempt randomizing music anyway, type OKAY at the prompt (case sensitive). Otherwise, music will not be randomized.")
        print("(found md5 {}, expected {})".format(sum, expected_sum))
        inp = input(" >")
        if inp == "OKAY":
            print("Proceeding with music randomization.")
            return True
    print("Music randomization cancelled.")
    return False
        
def dothething():
    lastcfg = configparser.ConfigParser(DEFAULT_DEFAULTS)
    lastcfg.read('lastused.cfg')
    
    def reseed(seed):
        print(f"seeding with {seed}")
        random.seed(seed+1)
        return seed+1
    
    seed = None
    inputfilename = None
    modes = ""
    
    print("Nascent Order supplemental randomizer for Final Fantasy VI by emberling")
    print("version {}".format(VERSION))
    print()
    if len(ARGS) >= 3:
        for arg in ARGS[2:]:
            try:
                seed = int(arg)
            except ValueError:
                modes = "{} {}".format(modes, arg).strip()
    if len(ARGS) >= 2:
        inputfilename = ARGS[1].strip()
        print("Using file {}".format(inputfilename))
    else:
        lastfile = lastcfg.get('LastUsed', 'lastfile')
        print("Enter ROM filename, or press enter to use the same one as last time.")
        inputfilename = input("Filename (default {}): ".format(lastfile))
        if not inputfilename: inputfilename = lastfile
    
    # read the file
    inputfile = False
    while not inputfile:
        try:
            inputfile = open(inputfilename, "rb")
        except IOError:
            print("File not found. Try another filename, or Ctrl-C to quit.")
            inputfilename = input("Enter rom filename: ")
    data = inputfile.read()
    inputfile.close()
    
    lastcfg.set('LastUsed', 'lastfile', inputfilename)
    
    # check for header, and adjust
    validbeginning = b"\x20\x79\x68\x6B\x03\x00"
    datastart = 0
    romsize = [s.strip() for s in CONFIG.get('GeneralPtr', 'romsize').split(',')]
    if len(romsize) != 2:
        romsize = to_default('romsize')
    romsize = [int(o, 16) for o in romsize]
    
    try:
        while True:
            dataleft = len(data) - datastart
            #dprint("dataleft {}   datastart {}".format(dataleft, datastart))
            assert (dataleft >= romsize[0] and dataleft <= romsize[1])
            if data[datastart:datastart+6] == validbeginning:
                break
            datastart += 1
    except (IndexError, AssertionError):
        print("This doesn't look like any FF6 ROM I've ever seen ...")
        print("Sorry, I don't know what to do with it!")
        print("(If you are using a very large expanded ROM (over 32mbit),")
        print("make sure to edit the config file to allow it.)")
        print('Type "yes" to keep going, anything else to abort.')
        if input("Continue? :") != "yes":
            quit()
    header = data[:datastart]
    data = data[datastart:]
    
    if not seed: seed = input("Enter seed, or press enter to use arbitrary seed: ").strip()
    try:
        seed = int(seed)
    except ValueError:
        print("Invalid seed entered, using default (timer)")
        seed = None
    if not seed: seed = int(time.time())
    print("Using seed {}".format(seed))
    print()
    random.seed(seed)
    vseed = seed
    
    # detect known romhacks
    hackconfig = configparser.ConfigParser()
    hackconfig.read('hackdetect.txt')
    for hack, infostr in hackconfig.items('HackDetection'):
        info = [s.strip() for s in infostr.split(',')]
        if len(info) >= 1:
            mightbe = True
            loc = int(info[0], 16)
            if loc >= (len(data) - len(info)):
                mightbe = False
                break
            for c in info[1:]:
                cmp = chr(int(c, 16))
                if data[loc] != cmp:
                    mightbe = False
                    break
                loc += 1
            if mightbe:
                print("detected applied hack: {}".format(hack))
                CONFIG.read("hd_"+hack+".txt")
                
    # pick options
    def getsavedmode(n, desc=False):
        return [s.strip() for s in lastcfg.get('LastUsed', 'mode'+str(n)).split(',')][1 if desc else 0]
        
    defaultmodes = [lastcfg.get('LastUsed', 'mlast').strip()] + [getsavedmode(n) for n in range(1,5)]
    defaultdescs = [""] + [getsavedmode(n, desc=True) for n in range(1,5)]
    if not modes:
        print()
        print("*** What do you want to do? ***")
        print("Type the letter for every option you want,")
        print("or press enter to use the same modes you used last time.")
        print()
        print("Last used modes: {}".format(defaultmodes[0]))
        print()
        print("Other saved modes:")
        for n in range(1,5):
            print("{} -- {}   {}".format(n, defaultmodes[n], "({})".format(defaultdescs[n]) if defaultdescs[n] else ""))
        print()
        print("Options: (lowercase)")
        print("  b - create battle music progression")
        print("  c - randomize character names, sprites, and portraits")
        # g - script edits reflecting characters' randomized identities
        print("  g - randomize guest character sprites, including Imp, Morph and Kefka")
        print("  i - add extended instruments")
        #print("  n - convert oldcharname to class, and other tiny misc NaO flavored fixes")
        print("  m - music randomizer")
        print("  n - randomize NPC sprites")
        print("  p - redo character palettes")
        # s - randomize spell effects and graphics????
        print("  w - (Worlds Collide sprite mode) *lightly* randomize character sprites and portraits, leaving characters recognizable")
        print("  x - replace placeholder portraits with zoomed-sprite portraits")
        print()
        print("  Include a number 1-4 to save selected modes in that slot for future use")
        print("keywords (all caps):")
        print("  MUSICCHAOS - songs that change choose from the entire pool of available songs")
        print("  ALTSONGLIST - uses songs_alt.txt instead of songs.txt for music config")
        print("  ONEWINGEDLEAFER - battle music progression based on level, not area (inconsistent)")
        print("  MESSMEUP - 'p' no longer applies updates to known incompatible sprites")
        print("  DISNEY - (p) advanced state-of-the-art cel shader mode")
        print("  GLOWSTICKS - (p) trance palettes for everyone")
        print("  PIXELPARTY - 'x' applies to all portraits")
        print("  TESTFILE - always outputs to mytest.[smc]")
        print("  TELLMEWHY - adds info about random pools to spoiler")
        print()
        modes = input("Select modes: ").strip()
    else:
        print("Using modes: {}".format(modes))
    
    modeschanged = True
    if len(modes) == 0:
        modes = defaultmodes[0]
        modeschanged = False
    if modes in list(map(str, list(range(1,5)))):
        #print "using slot {}: {}".format(modes, defaultmodes[int(modes)])
        modes = defaultmodes[int(modes)]
        
    # mode save config
    
    for i in range(1,5):
        if str(i) in modes:
            modes = re.sub('[1234,]', '', modes)
            print("Saving >{}< as quick access slot {}.".format(modes, i))
            descr = re.sub(',', '', input("Enter description: "))
            lastcfg.set('LastUsed', 'mode'+str(i), modes + ', ' + descr)
            break
    lastcfg.set('LastUsed', 'mlast', modes)
    
    with open('lastused.cfg', 'w') as cfg:
        lastcfg.write(cfg)
    
    print("Processing, using modes >{}<".format(modes))
    
    if len(data) <= 0x400000:
        data = data + b"\x00" * (0x400000 - len(data))
    
    # *** BEGIN ACTUALLY DOING THINGS ***
    
    if 'TELLMEWHY' in modes:
        global f_tellmewhy
        f_tellmewhy = True
    
    if 'ONEWINGEDLEAFER' in modes:
        FLAGS.add("battlebylevel")
    if 'PIXELPARTY' in modes:
        FLAGS.add('pixelparty')
    if 'n' in modes:
        FLAGS.add('miscfixes')
    if 'c' in modes:
        FLAGS.add('spriteimport')
    if 'x' in modes:
        FLAGS.add('portraits')
        
    if 'i' in modes:
        try:
            o_brrmeta = int(CONFIG.get('Music', 'brr_metadata_target_offset'),16)
        except ValueError:
            o_brrmeta = False
        data = insert_instruments(data, o_brrmeta)
            
    vseed = reseed(vseed)
    if 'm' in modes or 'b' in modes:
        if validate_custom_music(data):
            data = process_custom_music(data, f_randomize='m' in modes, f_battleprog='b' in modes, f_mchaos='MUSICCHAOS' in modes, f_altsonglist='ALTSONGLIST' in modes)
            if 'b' in modes:
                data = process_formation_music(data, 'NOFIELDSHUFFLE' not in modes)
    
    vseed = reseed(vseed)
    characters_to_replace = []
    if 'c' in modes or 'w' in modes:
        characters_to_replace.extend(list(range(14)))
    if 'g' in modes:
        characters_to_replace.extend(list(range(14,22)))
    if 'n' in modes:
        characters_to_replace.extend(list(range(22,0x3F)))
    if characters_to_replace:
        data = process_sprite_imports(data, characters_to_replace, rename=('c' in modes), id_restrict=('w' in modes))
        
    vseed = reseed(vseed)
    if 'p' in modes:
        #data = process_actor_events(data)
        data = process_char_palettes(data, 'DISNEY' in modes, 'GLOWSTICKS' in modes)
        if 'MESSMEUP' not in modes:
            data = process_sprite_fixes(data)
            
    vseed = reseed(vseed)
    if 'x' in modes:
        data = process_sprite_portraits(data, 'GENERALSTORE' in modes, 'PIXELPARTY' in modes)
    
    vseed = reseed(vseed)
    if 'p' in modes:
        data = process_actor_events(data)
        data = process_npcdb(data)
        
    #vseed = reseed(vseed)
    #if 'n' in modes:
    #    data = process_misc_fixes(data)
        
    vseed = reseed(vseed)
    if 'MANGLEMAGIC' in modes:
        data = mangle_magic(data)
        
    # *** END ACTUALLY DOING THINGS ***
        
    f_testfile = True if "TESTFILE" in modes else False
    
    outfileprefix = "".join(inputfilename.split('.')[:-1])
    extension = "".join(inputfilename.split('.')[-1:])
    for i in range(0,1000):
        outfilename = (outfileprefix + ".NaO{:03d}".format(i) + '.')  if not f_testfile else "mytest."
        if (not os.path.isfile(outfilename + extension)) or f_testfile:
            try:
                fo = open(outfilename + extension, "wb+")
                fo.write(data)
                fo.close()
                try:
                    fs = open(outfilename + 'txt', "w+")
                    printspoiler(fs, seed)
                    fs.close()
                except IOError:
                    print("couldn't write spoiler file")
                break
            except IOError:
                print("couldn't write output file " + outfilename + extension)
        if i == 999:
            print("couldn't create valid output file")
            break
            
if __name__ == "__main__":
    ARGS = list(sys.argv)
    CONFIG = configparser.RawConfigParser(CONFIG_DEFAULTS)
    random = random.Random()
    
    externtext = b' ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!?/:"`-.,_;#+()%~*@'
    #battletext = b"\xFE" + b"".join(map(bytes, list(range(0x80,0xD1))))
    battletext = b"\xFE" + bytes(range(0x80,0xD1))
    TO_BATTLETEXT = bytes.maketrans(externtext, battletext)
    FROM_BATTLETEXT = bytes.maketrans(battletext, externtext)
    try:
        CONFIG.read(os.path.join('custom','config.txt'))
        dothething()
        print()
        input("Processing complete. Press enter to close.")
    except Exception:
        #exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exc()  
        print()
        input("Processing failed. Press enter to close.")
        
