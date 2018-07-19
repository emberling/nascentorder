VERSION = "DEV 0.1.0"
DEBUG = True
import sys, traceback, ConfigParser, random, time, os.path, operator, hashlib, re
from copy import copy
from string import maketrans

HIROM = 0xC00000
defaultmode = 'bmx'
CONFIG_DEFAULTS = {
        'modes': defaultmode,
        'skip_hack_detection': 'False',
        'allow_music_repeats': 'False',
        'field_music_chance': '0',
        'preserve_song_data': 'False',
        'battle_music_lookup': 'battle1, boss1, boss2, battle2, battle3, 3B, battle4, battle5',
        'battle_music_ids': '24, new, new, new, new',
        'boss_music_ids': '14, 33',
        'pause_current_song': 'battle1, battle2, battle3, battle4, battle5',
        'romsize': '300000, 400200',
        'monsters_loc': 'F0000, F2FFF',
        'monsters_size': '20',
        'forms_loc': 'F6200, F83FF',
        'forms_size': '15',
        'forms_aux': 'F5900, F61FF',
        'forms_aux_size': '4',
        'songcount': '53C5E',
        'brrpointers': '53C5F, 53D1B',
        'songpointers': '53E96, 53F94',
        'instruments': '53F95, 54A34',
        'songpointerpointer': '50538',
        'instrumentpointer': '501E3',
        'songdata': '85C7A, 9FDFF, 352200',
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
        
spoiler = {}
f_tellmewhy = False
npcdb = {}

def dprint(msg):
    if DEBUG: print msg

    
def despoil(txt=""):
    global spoiler
    if 'Debug' not in spoiler: spoiler['Debug'] = []
    spoiler['Debug'].append(txt)
    
    
def byte_insert(data, position, newdata, maxlength=0, end=0):
    while position > len(data):
        data = data + "\x00"
    if end:
        maxlength = end - position + 1
    if maxlength and len(data) > maxlength:
        newdata = newdata[:maxlength]
    return data[:position] + newdata + data[position+len(newdata):]

    
def int_insert(data, position, newdata, length, reversed=True):
    n = int(newdata)
    l = []
    while len(l) < length:
        l.append(chr(n & 0xFF))
        n = n >> 8
    if n: dprint("WARNING: tried to insert {} into {} bytes, truncated".format(hex(newdata), length))
    if not reversed: l.reverse()
    return byte_insert(data, position, "".join(l), length)
    
def bytes_to_int(data, reversed=True):
    n = 0
    for i, d in enumerate(data):
        if reversed:
            n = n + (ord(d) << (8 * i))
        else:
            n = (n << (8 * i)) + ord(d)
    return n
    
    
def to_default(cfgname):
    print "WARNING: '{}' set incorrectly in config file, reverting to default".format(cfgname)
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
    handled.append('Debug')
    if DEBUG and 'Debug' in spoiler:
        line()
        line("DEBUG")
        line(separator)
        for t in spoiler['Debug']:
            line(t)
    for k in [sk for sk in spoiler if sk not in handled]:
        line()
        line(k)
        line(separator)
        for t in spoiler[k]:
            line(t)

            
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
    transtable = {tuple(v): k for k, v in huetranstable.items()}
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
    hues = map(hue_rgb, source_hues)
    while True:
        tryagain = False
        rng.shuffle(hues)
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
    data = data_in
    ## TODO clean this up
    # 2E85B1 '4C' -> '4F' keep Dark World song in WoR
    loc = 0x2E85B1
    if data[loc] == "\x4C":
        data = byte_insert(data, loc, "\x4F")
    
    # Restore or zero out class names
    loc = 0x3007DB
    if data[loc:loc+5] == "\x93\x84\x91\x91\x80":
        data = byte_insert(data, loc, "\xFF" * 0x70, end=0x30084A)
    
    return data
    
def process_sprite_fixes(data_in):
    data = data_in
    
    # Celes fix
    o_chains = 0x17D696
    o_newchains = 0x1587C0 + 0x6A * 32
    # Also uses offsets from checksums.cfg
    
    # Celes fix
    chains = data[o_newchains:o_newchains+32*6]
    data = byte_insert(data, o_chains, chains, 32*6)
    
    # ultros, chupon
    # recolors from /scratchpad
    checksumcfg = ConfigParser.ConfigParser()
    checksumcfg.read('checksums.cfg')
    fixes = [i[1] for i in checksumcfg.items('Sprites')]
    print fixes
    
    for fi in fixes:
        f = [s.strip() for s in fi.split(',')]
        if len(f) >= 4:
            offset, length = int(f[0], 16), int(f[1], 16)
            oldsprite = data[offset:offset+length]
            print "{} {}".format(f[3], hashlib.md5(oldsprite).hexdigest())
            if hashlib.md5(oldsprite).hexdigest() == f[2]:
                try:
                    with open(os.path.join("sprites", "fixes",f[3]), 'rb') as new:
                        newsprite = new.read(length)
                        data = byte_insert(data, offset, newsprite)
                except IOError:
                    print "couldn't read file {}".format(f[3])
                    continue
        else:
            print "WARNING: improperly formatted entry {} in checksums.cfg/sprites".format(f)
        #os.path.join("music", s.changeto + "_inst.bin"
        
    return data
    
def process_npcdb(data_in, f_sprites=False):
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
            s = ord(npcdata[loc+6])
            p = (ord(npcdata[loc+2]) & 0b00011100) >> 2
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
        s = ord(entry[6])
        p = (ord(entry[2]) & 0b00011100) >> 2
        if (s, p) in npcdb:
            news, newp = npcdb[(s, p)]
            newp = (newp << 2) | (ord(entry[2]) & 0b11100011)
            entry = byte_insert(entry, 2, chr(newp))
            entry = byte_insert(entry, 6, chr(news))
            
        loc += 9
    
    return data_in
    
def process_char_palettes(data_in, f_cel, f_rave):
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
    old_pals = map(ord, data[o_charpals:o_charpals+22])
    twinpal = rng.randint(0,5)
    char_palettes_forced = range(0,6) + range(1,6)
    char_palettes_forced.remove(twinpal)
    char_palettes_forced.append(random.choice(range(0,twinpal)+range(twinpal+1,6)))
    while char_palettes_forced[0] == twinpal or char_palettes_forced[1] == twinpal:
        rng.shuffle(char_palettes_forced)
    sprite_palettes = char_palettes_forced[:4] + [twinpal, twinpal, 0] + char_palettes_forced[4:]
    
    # by actor
    spritecfg = ConfigParser.ConfigParser()
    spritecfg.read('sprites.cfg')
    offsets = dict(spritecfg.items('EventSprites'))
    
    for c in xrange(0, 14):
        locs = [(o_menupals + c*18 + p) for p in [0, 4, 9, 13]] + [o_charpals + c]
        if hex(c)[2:] in offsets:
            locs.extend([int(s.strip(),16) for s in offsets[hex(c)[2:]].split(',')])
        for i, loc in enumerate(locs):
            p = sprite_palettes[c]
            if i < 4: p = (ord(data[loc]) & 0xF1) | ((sprite_palettes[c] + 2) << 1)
            data = int_insert(data, loc, p, 1)
    
    if 'moogles' in offsets:
        if offsets['moogles']:
            moogle_pals = range(0,6) * 2
            rng.shuffle(moogle_pals)
            for i, loc in enumerate([int(s.strip(),16) for s in offsets['moogles'].split(',')]):
                data = int_insert(data, loc, sprite_palettes[c], 1)

    print sprite_palettes
    print old_pals
    # by npc (processed elsewhere)
    for c in xrange(0,14):
        dif = sprite_palettes[c] - old_pals[c]
        while dif < 0: dif += 6
        while dif >= 6: dif -= 6
        for p in xrange(0,6):
            newpal = p + dif
            while newpal >= 6: newpal -= 6
            npcdb[c, p] = (c, newpal)
    for k in sorted(npcdb): print "k {}, v {}".format(k, npcdb[k])
    
    ## assign colors to palettes
    def components_to_color((red, green, blue)):
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
        hair_hue = char_hues_unused.pop(0)
        cloth_hue = char_hues_unused.pop(0)
        acc_hue = char_hues_unused.pop(0)
        new_palette = [[0,0,0], [3,3,3]] + list(skintone)
        new_palette = map(components_to_color, new_palette) * 4
        
        hair_sat = rng.choice([rng.randint(15,30), rng.randint(20,50), rng.randint(20,75)])
        hair_light = rng.choice([rng.randint(60,80), rng.randint(55,90)])
        hair_dark = rng.randint(int(hair_light * .5),int(hair_light * .65)) if hair_sat < 40 else \
                    rng.randint(int(hair_light * .45),int(hair_light * .52))
        new_palette[4] = components_to_color(hsv_approx(nudge_hue(hair_hue), hair_sat + rng.randint(-7,8), hair_light))
        new_palette[5] = components_to_color(hsv_approx(nudge_hue(hair_hue), hair_sat + rng.randint(-7,8), hair_dark))
        new_palette[2] = components_to_color(hsv_approx(nudge_hue(hair_hue), rng.randint(80,100), rng.randint(93,100)))
        new_palette[3] = components_to_color(hsv_approx(nudge_hue(hair_hue), rng.randint(10,100), rng.randint(10,25)))
        
        cloth_sat = rng.choice([rng.randint(10,50), rng.randint(30,60), rng.randint(10,85)])
        cloth_light = rng.randint(32, max(40,hair_dark + 5))
        cloth_dark = rng.randint(int(cloth_light * .6), int(cloth_light * .72))
        new_palette[8] = components_to_color(hsv_approx(nudge_hue(cloth_hue), cloth_sat + rng.randint(-7,8), cloth_light))
        new_palette[9] = components_to_color(hsv_approx(nudge_hue(cloth_hue), cloth_sat + rng.randint(-7,8), cloth_dark))
        
        acc_sat = rng.choice([rng.randint(10,25)] + [rng.randint(25,65)]*2 + [rng.randint(20,85)]*2)
        acc_light = rng.randint(cloth_light + 10,min(100,max(80,cloth_light + 20)))
        acc_dark = rng.randint(int(acc_light * .5), int(acc_light * .68)) if acc_sat < 50 else \
                   rng.randint(int(acc_light * .4), int(acc_light * .52))
        new_palette[10] = components_to_color(hsv_approx(nudge_hue(acc_hue), acc_sat + rng.randint(-7,8), acc_light))
        new_palette[11] = components_to_color(hsv_approx(nudge_hue(acc_hue), acc_sat + rng.randint(-7,8), acc_dark))
        
        hues = [guess_hue(hair_hue), guess_hue(cloth_hue), guess_hue(acc_hue)]
        used_range = set(xrange(hues[0]-15, hues[0]+15))
        used_range.update(set(xrange(hues[1]-15, hues[1]+15)))
        used_range.update(set(xrange(hues[2]-15, hues[2]+15)))
        used_range.update([n-360 for n in used_range if n > 360])
        town_hue = rng.choice([n for n in xrange(0,360) if n not in used_range])
        town_sat = rng.choice([rng.randint(10,50), rng.randint(30,50), rng.randint(10,65)])
        town_light = rng.randint(cloth_light, hair_light)
        town_dark = rng.randint(int(town_light * .6), int(town_light * .65))
        new_palette[12] = components_to_color(hsv_approx(nudge_hue(hue_rgb(town_hue)), town_sat + rng.randint(-7,8), town_dark))
        new_palette[13] = components_to_color(hsv_approx(nudge_hue(hue_rgb(town_hue)), town_sat + rng.randint(-7,8), town_light))
        
        used_range.update(xrange(town_hue-15, town_hue+15))
        aux_hue = rng.choice([n for n in xrange(0,360) if n not in used_range])
        aux_sat = rng.choice([rng.randint(15,30), rng.randint(20,50)])
        aux_light = rng.choice([rng.randint(min(town_light+15,90), 100), max(40, town_light - rng.randint(10,20))])
        aux_dark = rng.randint(int(aux_light * .55), int(aux_light * .65))
        new_palette[14] = components_to_color(hsv_approx(nudge_hue(hue_rgb(aux_hue)), town_sat + rng.randint(-7,8), aux_dark))
        new_palette[15] = components_to_color(hsv_approx(nudge_hue(hue_rgb(aux_hue)), town_sat + rng.randint(-7,8), aux_light))
        
        if f_cel:
            for i in [5, 7, 9, 11]:
                new_palette[i] = new_palette[i-1]
            for i in [12, 14]:
                new_palette[i] = new_palette[i+1]
        
        return new_palette
    
    def generate_trance_palette(f_cel):
        sign = rng.choice([1, -1])
        hues = [rng.randint(0,360)] # skin
        hues.append(hues[0] + rng.randint(15,60) * sign) # hair
        hues.append(hues[1] + rng.randint(15,60) * sign) # clothes
        hues.append(hues[2] + rng.randint(15,60) * sign) # acc
        hues.append(rng.randint(0,360)) #town
        hues.append(rng.randint(0,360)) #aux
        
        new_palette = [[0, 0, 0], [3, 3, 3]] * 8
        
        sats, vals = [], []
        for i, h in enumerate(hues):
            while hues[i] < 0: hues[i] += 360
            while hues[i] >= 360: hues[i] -= 360
            sats.append(rng.randint(80,100))
            vals.append(rng.randint(80,100))
        
        new_palette[2]  = [31, 31, 31]
        new_palette[3]  = hsv_approx(nudge_hue(hue_rgb(hues[1])), sats[1], rng.randint(15,30))
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
                
        return map(components_to_color, new_palette)

    skintonesraw = [v for k, v in spritecfg.items('SkinColor')]
    skintones = []
    for s in skintonesraw:
        components = [int(t.strip()) for t in s.split(',')]
        skintones.append(tuple((tuple(components[0:3]), tuple(components[3:6]))))
    
    rng.shuffle(skintones)
    
    new_palettes = []
    for p in xrange(0,6):
        if f_rave:
            new_palettes.append(generate_trance_palette(f_cel))
        else:
            new_palettes.append(generate_normal_palette(skintones.pop(), f_cel))
    trance = generate_trance_palette(f_cel)
    
    for i, p in enumerate(new_palettes + [trance]):
        bin = '\x00' * 32
        for j, c in enumerate(p):
            bin = int_insert(bin, j*2, c, 2)
        data = byte_insert(data, o_fpaldata + (8 if i==6 else i)*32, bin, 32)
        data = byte_insert(data, o_bpaldata + i*32, bin, 32)
    
    return data
        
def process_custom_music(data, f_randomize, f_battleprog, f_mchaos, f_altsonglist):
    print "** Processing random music ..." if f_randomize else "** Processing custom music ..."
    f_repeat = CONFIG.getboolean('Music', 'allow_music_repeats')
    f_preserve = CONFIG.getboolean('Music', 'preserve_song_data')
    isetlocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'instruments').split(',')]
    if len(isetlocs) != 2: isetlocs = to_default('instruments')
    songdatalocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'songdata').split(',')]
    starts = songdatalocs[::2]
    ends = songdatalocs[1::2]
    if len(ends) < len(starts): ends.append(0x3FFFFF)
    songdatalocs = zip(starts, ends)
    native_prefix = "ff6_"
    isetsize = 0x20
    
    def spoil(txt):
        global spoiler
        if 'Music' not in spoiler: spoiler['Music'] = []
        spoiler['Music'].append(txt)
    
    def spooler(txt):
        global spoiler, f_tellmewhy
        if f_tellmewhy:
            if 'MusicPools' not in spoiler: spoiler['MusicPools'] = []
            spoiler['MusicPools'].append(txt)
            
    class SongSlot:
        def __init__(self, id, chance=0, is_pointer=True, data="\x00\x00\x00"):
            self.id = id
            self.chance = chance
            self.choices = []
            self.changeto = ""
            self.is_pointer = is_pointer
            self.data = data
            self.inst = ""
            
    # figure out what instruments are available
    sampleptrs = [s.strip() for s in CONFIG.get('MusicPtr', 'brrpointers').split(',')]
    if len(sampleptrs) != 2: sampleptrs = to_default('brrpointers')
    instcount = (int(sampleptrs[1],16) + 1 - int(sampleptrs[0],16)) / 3
    
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
    
    songcount = [ord(data[songcountloc])]
    while i < songcount[0]:
        try: p = songptrdata[i*3:i*3+3]
        except IndexError: p = '\x00\x00\x00'
        songptrs.append(bytes_to_int(p) - HIROM)
        i += 1
        
    # build identifier table
    songconfig = ConfigParser.ConfigParser()
    songconfig.read('defaultsongs.txt')
    songconfig.read('songs.txt' if not f_altsonglist else 'songs_alt.txt')
    songtable = {}
    for ss in songconfig.items('SongSlots'):
        vals = [s.strip() for s in ss[1].split(',')]
        songtable[vals[0]] = SongSlot(int(ss[0],16), chance=int(vals[1]))
    
    # determine which songs change
    used_songs = []
    songs_to_change = []
    for ident, s in songtable.items():
        if rng.randint(1, 100) > s.chance:
            if not f_repeat: used_songs.append(native_prefix + ident)
            songtable[ident].changeto = native_prefix + ident
        else:
            songs_to_change.append((ident, s))
            
    # build choice lists
    intensitytable = {}
    for song in songconfig.items('Imports'):
        canbe = [s.strip() for s in song[1].split(',')]
        intense, epic = 0, 0
        if f_mchaos:
            for ident, s in songtable.items():
                s.choices.append(song[0])
        for c in canbe:
            if not c: continue
            if c == "CONVERT":
                pass #TODO
            elif c[0] == "I":
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
                    songtable[ch].choices.extend([song[0]]*mult)
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
        for i, id in enumerate(battleids):
            if str(id).lower() == "new":
                songtable['NaObattle' + str(newidx)] = SongSlot(nextsongid, chance=100)
                battleids[i] = nextsongid
                nextsongid += 1
                newidx += 1
            else:
                battleids[i] = int(id, 16)
        newidx = 0
        for i, id in enumerate(bossids):
            if str(id).lower() == "new":
                songtable['NaOboss' + str(newidx)] = SongSlot(nextsongid, chance=100)
                bossids[i] = nextsongid
                nextsongid += 1
                newidx += 1
            else:
                bossids[i] = int(id, 16)
        
        # what this is trying to do is:
        # we judge songs by pure INTENSITY or by combined INTENSITY and GRANDEUR
        # old method:
        # the lowest combined rating song is our first battle music
        # the highest combined rating song is our last boss music
        # remaining songs are separated by pure intensity into battle and boss
        # new method: all songs separated by pure intensity into battle and boss
        # within these categories they are set in combined rating order
        battlecount = len(battleids) + len(bossids)
        while len(intensitytable) < battlecount:
            dprint("WARNING: not enough battle songs marked, adding random song to pool")
            newsong = rng.choice([k[0] for k in songconfig.items('Imports') if k not in intensitytable])
            intensitytable[newsong] = (rng.randint(0,9), rng.randint(0,9))
        retry = True
        while retry:
            retry = False
            battlechoices = rng.sample([(k, sum(intensitytable[k]), intensitytable[k][0]) for k in intensitytable.keys()], battlecount)
            for c in battlechoices:
                if battlechoices[0] in used_songs: retry = True
        battlechoices.sort(key=operator.itemgetter(1))
        battleprog = [None]*len(battleids)
        bossprog = [None]*len(bossids)
        #battleprog[0] = battlechoices.pop(0)
        #bossprog[0] = battlechoices.pop(-1)
        bosschoices = []
        battlechoices.sort(key=operator.itemgetter(2))
        for i in xrange(0, len(bossids)):
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
        
        fightids = [(id, False) for id in battleids] + [(id, True) for id in bossids]
        for id, is_boss in fightids:
            for ident, s in songtable.items():
                if s.id == id:
                    if is_boss:
                        changeto = bossprog[bossids.index(id)]
                    else:
                        changeto = battleprog[battleids.index(id)]
                    s.changeto = changeto
                    used_songs.append(changeto)

        return (battleids, bossids)
    
    def check_ids_fit():
        n_by_isets = (isetlocs[1] - isetlocs[0] + 1) / 0x20
        n_by_sptrs = (songptraddrs[1] - songptraddrs[0] + 1) / 3
        #print "songtable {} isets {} sptrs {}".format(len(songtable), n_by_isets, n_by_sptrs)
        if len(songtable) > n_by_isets or len(songtable) > n_by_sptrs:
            return False
        return True
        
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
        used_songs = copy(used_songs_backup)
        songtable = copy(songtable_backup)
        songs_to_change = copy(songs_to_change_backup)
        set_by_battleprog = []
        if f_battleprog:
            battleprog = process_battleprog()
            set_by_battleprog = battleprog[0] + battleprog[1]
        songs_to_change = [s for s in songs_to_change if s[1].id not in set_by_battleprog]
        f_moveinst = False if check_ids_fit() or f_preserve else True
        rng.shuffle(songs_to_change)
        for ident, s in songs_to_change:
            choices = [c for c in songtable[ident].choices if c not in used_songs]
            if not choices: choices.append(native_prefix + ident)
            newsong = rng.choice(choices)
            if (newsong in used_songs) and (not f_repeat):
                keeptrying = True
                break
            else:
                if not f_repeat: used_songs.append(newsong)
                songtable[ident].changeto = newsong if f_randomize else native_prefix + ident
                
        if keeptrying:
            dprint("failed music generation during song selection")
            continue
        
        #get data now, so we can keeptrying if there's not enough space
        for ident, s in songtable.items():
            # case: get song from source ROM
            if not os.path.isfile(os.path.join("music", s.changeto + "_data.bin")):
                target = s.changeto[len(native_prefix):]
                if (s.changeto[:len(native_prefix)] == native_prefix and
                        target in songtable):
                    sid = songtable[target].id
                    loc = songptrs[sid]
                    assert loc >= min([l[0] for l in songdatalocs])
                    if f_preserve:
                        s.is_pointer = True
                        s.data = loc
                    else:
                        s.is_pointer = False
                        slen = bytes_to_int(data[loc:loc+2]) + 2
                        #if data[loc+slen-1] == '\xF6': slen = slen + 2
                        #if data[loc+slen-2] == '\xF6': slen = slen + 1
                        s.data = data[loc:loc+slen]
                    loc = isetlocs[0] + sid * isetsize
                    assert loc + isetsize <= isetlocs[1] + 1
                    s.inst = data[loc:loc+isetsize]
                else:
                    print "target song {} not found for id {} {}".format(s.changeto, s.id, ident)
                    keeptrying = True
                    break
            else:
                s.is_pointer = False
                # check instrument validity
                try:
                    fi = open(os.path.join("music", s.changeto + "_inst.bin"), "rb")
                    s.inst = fi.read()
                    fi.close()
                except IOError:
                    print "couldn't open {}_inst.bin".format(s.changeto)
                    keeptrying = True
                    break
                if max(map(ord, s.inst)) > instcount:
                    # case: get nopatch version
                    try:
                        fi = open(os.path.join("music", s.changeto + "_inst_nopatch.bin"), "rb")
                        s.inst = fi.read()
                        fi.close()
                    except IOError:
                        dprint("translating inst file for id{} {}".format(s.id, s.changeto))
                        #s.inst = translate_inst(ibin) #TODO
                        dprint("translation is NYI")
                    try:
                        fi = open(os.path.join("music", s.changeto + "_data_nopatch.bin"), "rb")
                        s.data = fi.read()
                        fi.close()
                    except IOError:
                        try:
                            fi = open(os.path.join("music", s.changeto + "_data.bin"), "rb")
                            s.data = fi.read()
                            fi.close()
                        except IOError:
                            print "couldn't open {}_data.bin".format(s.changeto)
                            keeptrying = True
                            break
                else:
                    # case: get standard version
                    try:
                        fi = open(os.path.join("music", s.changeto + "_data.bin"), "rb")
                        s.data = fi.read()
                        fi.close()
                    except IOError:
                        print "couldn't open {}_data.bin".format(s.changeto)
                        keeptrying = True
                        break
        
        if keeptrying:
            dprint("failed music generation during data read")
            continue
        
        # try to fit it all in!
        if f_preserve:
            freelocs = []
            for b, e in songdatalocs:
                i = b
                lastchar = ''
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
        songdata = [""] * len(space)
        songinst = data[isetlocs[0]:isetlocs[1]+1]    
        dprint("    free space for music: {}".format(space))
        for ident, s in songtable.items():
            #dprint("attempting to insert {} in slot {} ({})".format(s.changeto, s.id, ident))
            for i, l in enumerate(songdatalocs):
                if not s.is_pointer:
                    if space[i] >= len(s.data):
                        insertloc = l[0] + len(songdata[i])
                        songdata[i] += s.data
                        space[i] -= len(s.data)
                        songinst = byte_insert(songinst, s.id * isetsize, s.inst, isetsize)
                        songptrdata = int_insert(songptrdata, s.id * 3, insertloc + HIROM, 3)
                        songlocations[s.id] = insertloc
                        break
                else:
                    songptrdata = int_insert(songptrdata, s.id * 3, s.data, 3)
                    songlocations[s.id] = s.data - HIROM
                    break
                    
    if attempts >= 1000:
        print "failed to produce valid music set"
        print "    try increasing available space or adjusting song insert list"
        print "    to use less space"
        print
        return data
    
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
        
        battletable = "".join(map(chr, battletable))
        pausetable = "".join(map(chr, pausetable))
        
        
    # write to rom
    if f_moveinst:
        #songptrptr = int(CONFIG.get('MusicPtr', 'songpointerpointer'), 16)
        #don't need to move song pointers because we are assuming it can just
        #extend into the instrument space we are now freeing. may need to
        #add contingency for if they are already separate later.
        instlocptr = int(CONFIG.get('MusicPtr', 'instrumentpointer'), 16)
        data = int_insert(data, instlocptr, new_instloc[0] + HIROM, 3)
        
    if f_battleprog:
        data = byte_insert(data, pausetableloc, pausetable, 5)
        data = byte_insert(data, battlesongsloc, battletable, 8)
    data = int_insert(data, songcountloc, len(songtable)+1, 1)
    if not f_moveinst: songptrdata = songptrdata[:songptraddrs[1] + 1]
    data = byte_insert(data, songptraddrs[0], songptrdata)
    if f_moveinst:
        data = byte_insert(data, new_instloc[0], songinst, end=new_instloc[1])
    else:
        data = byte_insert(data, isetlocs[0], songinst, end=isetlocs[1])
    for i, l in enumerate(songdatalocs):
        data = byte_insert(data, l[0], songdata[i], end=l[1])
    
    # make spoiler
    changed_songs = {}
    for ident, s in songtable.items():
        if s.changeto != native_prefix + ident:
            changed_songs[s.id] = (ident, s.changeto)
    spoiltext = []
    for id, s in sorted(changed_songs.items()):
        spoiltext.append(hex(id)[2:] + " : " + s[0] + " ")
    arrowpos = max(map(len, spoiltext))
    for i, (id, s) in enumerate(sorted(changed_songs.items())):
        while len(spoiltext[i]) < arrowpos:
            spoiltext[i] += " "
        spoiltext[i] += "-> {}".format(s[1])
    for t in spoiltext: spoil(t)
    
    if DEBUG:
        fullsonglist = {}
        for ident, s in songtable.items():
            fullsonglist[s.id] = (ident, s.changeto, songlocations[s.id])
        despoil("song data locations")
        for id, (ident, newsong, loc) in fullsonglist.items():
            despoil("{} ({}) -----> {} at {}".format(hex(id), ident, newsong, hex(loc)))
    return data
    
def process_formation_music(data, f_shufflefield):
    print "** Processing progressive battle music ..."
    isetlocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'instruments').split(',')]
    if len(isetlocs) != 2: isetlocs = to_default('instruments')
    songdatalocs = [int(s.strip(),16) for s in CONFIG.get('MusicPtr', 'songdata').split(',')]
    starts = songdatalocs[::2]
    ends = songdatalocs[1::2]
    if len(ends) < len(starts): ends.append(0x3FFFFF)
    songdatalocs = zip(starts, ends)
    native_prefix = "ff6_"
    isetsize = 0x20
    
    # build table of monster levels
    monsterlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'monsters_loc').split(',')]
    if len(monsterlocs) != 2: monsterlocs = to_default('monsters_loc')
    monstersize = int(CONFIG.get('EnemyPtr', 'monsters_size'), 16)
    
    monstercount = (monsterlocs[1] + 1 - monsterlocs[0]) / monstersize
    monsterlevels = []
    for i in xrange(0, monstercount):
        levelloc = monsterlocs[0] + (i * monstersize) + 0x10
        monsterlevels.append(ord(data[levelloc]))
        
    # build table of average levels within formations
    formlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'forms_loc').split(',')]
    if len(formlocs) != 2: formlocs = to_default('forms_loc')
    formsize = int(CONFIG.get('EnemyPtr', 'forms_size'), 16)
    
    formcount = (formlocs[1] + 1 - formlocs[0]) / formsize
    formlevels = []
    forms = [] #debug
    for i in xrange(0, formcount):
        loc = formlocs[0] + (i * formsize)
        flags = data[loc+1]
        form = data[loc+2:loc+8]
        levels = []
        for j in xrange(0,6):
            if ord(flags) & (1 << j):
                levels.append(monsterlevels[ord(form[j])])
        if levels: 
            formlevels.append(sum(levels) / len(levels))
        else:
            formlevels.append(0)
        forms.append(map(ord, form)) #debug
                
    # iterate aux form data and:
    #   if music is 1, chance to change it to 2
    #   if it's 0/3/4/6/7, set according to level percentile
    auxlocs = [int(s.strip(),16) for s in CONFIG.get('EnemyPtr', 'forms_aux').split(',')]
    if len(monsterlocs) != 2: monsterlocs = to_default('forms_aux')
    auxsize = int(CONFIG.get('EnemyPtr', 'forms_aux_size'), 16)
    auxdata = data[auxlocs[0]:auxlocs[1]+1]
    formsongs = [] #debug
    for i in xrange(0, formcount):
        loc = i * auxsize + 3
        byte = ord(auxdata[loc])
        keepfield = byte >> 7
        song = (byte >> 4) & 0b0111
        maxlevel = max(formlevels)
        if song == 1 and not keepfield:
            if rng.randint(0, 20 + maxlevel) < (20 + formlevels[i]):
                song = 2
                byte = (byte & 0b10001111) | (song << 4)
        elif song != 5:
            tier = maxlevel / 5
            if formlevels[i] >= tier * 4: song = 7
            elif formlevels[i] >= tier * 3: song = 6
            elif formlevels[i] >= tier * 2: song = 4
            elif formlevels[i] >= tier * 1: song = 3
            else: song = 0
            byte = (byte & 0b10001111) | (song << 4)
            if f_shufflefield:
                fieldchance = int(CONFIG.get('Music', 'field_music_chance').strip())
                if fieldchance > 100 or fieldchance < 0: fieldchance = to_default('field_music_chance')
                if rng.randint(1,100) > fieldchance:
                    byte &= 0b01111111
                    fanfare = True
                else:
                    byte |= 1 << 7
                    fanfare = False
                fanbyte = ord(auxdata[loc-2])
                if fanfare:
                    fanbyte &= 0b11111101
                else:
                    fanbyte |= 0b10
                auxdata = byte_insert(auxdata, loc-2, chr(fanbyte))
        formsongs.append(song)
        auxdata = byte_insert(auxdata, loc, chr(byte))

    if DEBUG:
        for i in xrange(0, monstercount):
            despoil("monster {} is level {}".format(i, monsterlevels[i]))
        for i in xrange(0, formcount):
            despoil()
            despoil("FORMATION {} assigned song {}".format(i, formsongs[i]))
            despoil("contains {} :: avg {}".format(forms[i], formlevels[i]))
    return byte_insert(data, auxlocs[0], auxdata, end=auxlocs[1])

def process_sprite_portraits(data_in, f_merchant=False, f_changeall=False):
    print "** Processing sprite portraits ..."
    data = data_in
    
    def tile_to_pixels(tile):
        out = []
        for r in range(0,8):
            row = []
            for c in range(0,8):
                pixel = ( ord(tile[r*2]) >> (7-c) ) & 0x1
                pixel += ( ( ord(tile[r*2+1]) >> (7-c) ) & 0x1 ) << 1
                pixel += ( ( ord(tile[r*2+16]) >> (7-c) ) & 0x1 ) << 2
                pixel += ( ( ord(tile[r*2+17]) >> (7-c) ) & 0x1 ) << 3
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
        if set(data[loc:loc+64]) == set("\x00"):
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
                data = byte_insert(data, loc, "".join(map(chr,pixels_to_tile(btiles[r][c]))))
        
        loc = o_charpalptrs + sid
        palid = ord(data[loc])
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
    hashcfg = ConfigParser.ConfigParser()
    hashcfg.read("checksums.cfg")
    porthashtbl = [[j.strip() for j in i[1].split(',')] for i in hashcfg.items('Portraits')]
    porthashtbl = [h for h in porthashtbl if len(h) > 1]
    porthashes = [h[0] for h in porthashtbl]
    print "{} placeholder hashes identified".format(len(porthashes))
    spriterecord = {}
    if f_changeall:
        changemap = [True] * 19
    else:
        changemap = [False] * 19
        for p in xrange(0,21):
            print "P {}".format(p)
            if p in [18, 19]: continue
            pp = 18 if p == 20 else p
            pid = ord(data[o_portptrs + p])
            sid = p #sid = 20 if pid == 18 else pid
            loc = o_portraits + 0x320 * ord(data[o_portptrs + p])
            thisport = data[loc:loc+0x320]
            
            thishash = hashlib.md5(thisport).hexdigest()
            print "got portrait {} -- md5 {}".format(pid, thishash)
            if thishash in porthashes:
                spritehashes = porthashtbl[porthashes.index(thishash)][1:]
                print "hash match (known ph). {} sprite hashes identified: {}".format(len(spritehashes), spritehashes)
                sloc = o_spritesheet + (min(sid,16) * o_spritesizea) + (max(0,sid-16) * o_spritesizeb)
                thissprite = data[sloc:sloc+o_spritesizeb]
                shash = hashlib.md5(thissprite).hexdigest()
                print "got sprite {} -- len {} md5 {}".format(sid, len(thissprite), shash)
                if shash not in spritehashes:
                    print "sprite not approved for placeholder. setting to change"
                    changemap[pp] = True
                else:
                    thisidx = spritehashes.index(shash)
                    if shash in spriterecord:
                        if spriterecord[shash][1] <= thisidx:
                            print "{} found in record, supersedes idx{}".format(spriterecord[shash][1],thisidx)
                            changemap[pp] = True
                        else:
                            changemap[spriterecord[shash][0]] = False
                            spriterecord[shash] = (pid, thisidx)
                            print "recorded {} for {}".format(spriterecord[shash], shash)
            elif thisport in orig_portraits:
                print "this duplicates pid {}, setting to change".format(orig_portraits.index(thisport))
                changemap[pp] = True
                print changemap
            orig_portraits.append(thisport)
            
            loc = o_portpals + pid * 32
            thispal = data[loc:loc+32]
            orig_palettes.append(thispal)

            
    for p in xrange(0,19):
        if changemap[p]:
            data = paint_portrait(data, p)
        else:
            loc = o_portraits + p * 0x320
            data = byte_insert(data, loc, orig_portraits[p], 0x320)
            loc = o_portpals + p * 32
            data = byte_insert(data, loc, orig_palettes[p], 32)
        
    # fix BC v64 messing up portrait pointers
    loc = o_portptrs
    pt = (range(0, 0x10) + ([0xE] if f_merchant else [0x10]) + [0x11, 0] +
            ([0x10] if f_merchant else [1]) + [0x12, 0, 0, 0, 0, 0, 6])
    porttable = "".join(map(chr, pt))
    for i in xrange(0,0x1B):
        porttable = int_insert(porttable, len(porttable), 0x320*pt[i], 2)
    data = byte_insert(data, loc, porttable, 0x4F)
    
    assert len(data_in) == len(data)
    return data

# tool to help exploratory design on a far future mode
# not for public but if you find this and want to try it, knock yrself out
def mangle_magic(data_in):
    data = data_in
    
    #             [sprite] [ bg1 ] [ bg3 ] [palettes ] sfx ini [esper] spd
    sanim_base = "\x7E\x02\xFF\xFF\xFF\xFF\x9D\x9D\x9D\x16\x1B\xFF\xFF\x10"
    spell_base = "\x21\x00\x28\x09\x21\x05\x0A\x00\x00\xFF\x00\x00\x00\x00"
    
    animtable = ConfigParser.ConfigParser()
    animtable.read('sdev')
    
    layertbl = {}
    for lyr in ['1', '2', '3', '4']:
        print lyr
        for i, d in enumerate(animtable.get('sdev', lyr).split()):
            print "{}: {} {}".format(i, type(d), d)
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
    
        
def dothething():
    lastcfg = ConfigParser.ConfigParser(DEFAULT_DEFAULTS)
    lastcfg.read('lastused.cfg')
    
    print "Nascent Order supplemental randomizer for Final Fantasy VI by emberling"
    print "version {}".format(VERSION)
    print
    if len(ARGS) > 2:
        inputfilename = args[1].strip()
    else:
        lastfile = lastcfg.get('LastUsed', 'lastfile')
        print "Enter ROM filename, or press enter to use the same one as last time."
        inputfilename = raw_input("Filename (default {}): ".format(lastfile))
        if not inputfilename: inputfilename = lastfile
    
    # read the file
    inputfile = False
    while not inputfile:
        try:
            inputfile = open(inputfilename, "rb")
        except IOError:
            print "File not found. Try another filename, or Ctrl-C to quit."
            inputfilename = raw_input("Enter rom filename: ")
    data = inputfile.read()
    inputfile.close()
    
    lastcfg.set('LastUsed', 'lastfile', inputfilename)
    
    # check for header, and adjust
    validbeginning = "\x20\x79\x68\x6B\x03\x00"
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
    except IndexError, AssertionError:
        print "This doesn't look like any FF6 ROM I've ever seen ..."
        print "Sorry, I don't know what to do with it!"
        print "(If you are using a very large expanded ROM (over 32mbit),"
        print "make sure to edit the config file to allow it.)"
        print 'Type "yes" to keep going, anything else to abort.'
        if raw_input("Continue? :") != "yes":
            quit()
    header = data[:datastart]
    data = data[datastart:]
    
    seed = raw_input("Enter seed, or press enter to use arbitrary seed: ").strip()
    if not seed: seed = int(time.time())
    seed = int(seed)
    print "Using seed {}".format(seed)
    print
    rng.seed(seed)
    random = rng
    
    # detect known romhacks
    hackconfig = ConfigParser.ConfigParser()
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
                print "detected applied hack: {}".format(hack)
                CONFIG.read("hd_"+hack+".txt")
                
    # pick options
    def getsavedmode(n, desc=False):
        return [s.strip() for s in lastcfg.get('LastUsed', 'mode'+str(n)).split(',')][1 if desc else 0]
        
    defaultmodes = [lastcfg.get('LastUsed', 'mlast').strip()] + [getsavedmode(n) for n in range(1,5)]
    defaultdescs = [""] + [getsavedmode(n, desc=True) for n in range(1,5)]
    print
    print "*** What do you want to do? ***"
    print "Type the letter for every option you want,"
    print "or press enter to use the same modes you used last time."
    print
    print "Last used modes: {}".format(defaultmodes[0])
    print
    print "Other saved modes:"
    for n in xrange(1,5):
        print "{} -- {}   {}".format(n, defaultmodes[n], "({})".format(defaultdescs[n]) if defaultdescs[n] else "")
    print
    print "Options: (lowercase)"
    print "  b - create battle music progression"
    # c - randomize character names, sprites, and portraits
    # g - script edits reflecting characters' randomized identities
    print "  n - convert oldcharname to class, and other tiny misc NaO flavored fixes"
    print "  m - music randomizer"
    print "  p - redo character palettes"
    # s - randomize spell effects and graphics????
    print "  x - replace placeholder portraits with zoomed-sprite portraits"
    print
    print "  Include a number 1-4 to save selected modes in that slot for future use"
    print "keywords (all caps):"
    print "  MUSICCHAOS - songs that change choose from the entire pool of available songs"
    print "  ALTSONGLIST - uses songs_alt.txt instead of songs.txt for music config"
    print "  NOFIELDSHUFFLE - 'b' no longer changes which battles continue field music"
    print "  MESSMEUP - 'p' no longer applies updates to known incompatible sprites"
    print "  PIXELPARTY - 'x' applies to all portraits"
    print "  TESTFILE - always outputs to mytest.[smc]"
    print "  TELLMEWHY - adds info about random pools to spoiler"
    print
    modes = raw_input("Select modes: ").strip()
    
    
    modeschanged = True
    if len(modes) == 0:
        modes = defaultmodes[0]
        modeschanged = False
    if modes in map(str, range(1,5)):
        #print "using slot {}: {}".format(modes, defaultmodes[int(modes)])
        modes = defaultmodes[int(modes)]
        
    # mode save config
    
    for i in xrange(1,5):
        if str(i) in modes:
            modes = re.sub('[1234,]', '', modes)
            print "Saving >{}< as quick access slot {}.".format(modes, i)
            descr = re.sub(',', '', raw_input("Enter description: "))
            lastcfg.set('LastUsed', 'mode'+str(i), modes + ', ' + descr)
            break
    lastcfg.set('LastUsed', 'mlast', modes)
    
    with open('lastused.cfg', 'w') as cfg:
        lastcfg.write(cfg)
    
    print "Processing, using modes >{}<".format(modes)
    
    if len(data) <= 0x400000:
        data = data + "\x00" * (0x400000 - len(data))
    
    # *** BEGIN ACTUALLY DOING THINGS ***
    
    if 'TELLMEWHY' in modes:
        global f_tellmewhy
        f_tellmewhy = True
        
    if 'm' in modes or 'b' in modes:
        data = process_custom_music(data, 'm' in modes, 'b' in modes, 'MUSICCHAOS' in modes, 'ALTSONGLIST' in modes)
        if 'b' in modes:
            data = process_formation_music(data, 'NOFIELDSHUFFLE' not in modes)
    
    if 'p' in modes:
        data = process_char_palettes(data, 'DISNEY' in modes, 'GLOWSTICKS' in modes)
        if 'MESSMEUP' not in modes:
            data = process_sprite_fixes(data)
            
    if 'x' in modes:
        data = process_sprite_portraits(data, 'GENERALSTORE' in modes, 'PIXELPARTY' in modes)
    
    if 'p' in modes:
        data = process_npcdb(data)
        
    if 'n' in modes:
        data = process_misc_fixes(data)
        
    if 'MANGLEMAGIC' in modes:
        data = mangle_magic(data)
        
    # *** END ACTUALLY DOING THINGS ***
        
    f_testfile = True if "TESTFILE" in modes else False
    
    outfileprefix = "".join(inputfilename.split('.')[:-1])
    extension = "".join(inputfilename.split('.')[-1:])
    for i in xrange(0,1000):
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
                    print "couldn't write spoiler file"
                break
            except IOError:
                print "couldn't write output file " + outfilename + extension
        if i == 999:
            print "couldn't create valid output file"
            break
            
if __name__ == "__main__":
    ARGS = list(sys.argv)
    CONFIG = ConfigParser.RawConfigParser(CONFIG_DEFAULTS)
    rng = random.Random()
    
    externtext = ' ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!?/:"`-.,_;#+()%~*@'
    battletext = "\xFE" + "".join(map(chr, range(0x80,0xD1)))
    TO_BATTLETEXT = maketrans(externtext, battletext)
    FROM_BATTLETEXT = maketrans(battletext, externtext)
    try:
        CONFIG.read('config.txt')
        dothething()
        print
        raw_input("Processing complete. Press enter to close.")
    except Exception:
        #exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exc()  
        print
        raw_input("Processing failed. Press enter to close.")
        
