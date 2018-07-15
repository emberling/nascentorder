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
        f_moveinst = False if check_ids_fit() else True
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
            instsize = len(songtable) * 0x20
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
    data = int_insert(data, songcountloc, len(songtable), 1)
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
        #if pid >= 16: sloc -= 0x140 * (sid-16) # leo/banon/ghost/etc spritesheets are smaller
        
        #fout.seek(sloc + 32 * 0x3E)
        loc = sloc + 32 * 0x3E
        tiles = []
        if set(data[loc:loc+64]) == set("\x00"):
            loc += 64
        for t in range(0,4):
            #tiles.append(fout.read(32))
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
                #fout.seek(offset + pos)
                #fout.write("".join(map(chr,pixels_to_tile(btiles[r][c]))))
                loc = offset + pos
                data = byte_insert(data, loc, "".join(map(chr,pixels_to_tile(btiles[r][c]))))
        
        #fout.seek(0x02CE2B + sid)
        #palid = ord(fout.read(1))
        #fout.seek(0x2D6300 + palid * 32)
        #palette = fout.read(32)
        #fout.seek(0x2D5860 + pid * 32)
        #fout.write(palette)
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
    # g - randomize character genders (includes script edits)
    print "  m - music randomizer"
    # p - redo character palettes
    # s - randomize spell effects and graphics????
    print "  x - replace placeholder portraits with zoomed-sprite portraits"
    print
    print "  Include a number 1-4 to save selected modes in that slot for future use"
    print "keywords (all caps):"
    print "  MUSICCHAOS - songs that change choose from the entire pool of available songs"
    print "  ALTSONGLIST - uses songs_alt.txt instead of songs.txt for music config"
    print "  NOFIELDSHUFFLE - 'b' no longer changes which battles continue field music"
    #print "  GENERALSTORE - 'x' produces a merchant portrait using Leo's slot"
    print "  PIXELPARTY - 'x' applies to all portraits"
    print "  TESTFILE - always outputs to mytest.[smc]"
    print "  TELLMEWHY - add info random pools to spoiler"
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
    
    # *** BEGIN ACTUALLY DOING THINGS ***
    
    if 'TELLMEWHY' in modes:
        global f_tellmewhy
        f_tellmewhy = True
        
    if 'm' in modes or 'b' in modes:
        data = process_custom_music(data, 'm' in modes, 'b' in modes, 'MUSICCHAOS' in modes, 'ALTSONGLIST' in modes)
        if 'b' in modes:
            data = process_formation_music(data, 'NOFIELDSHUFFLE' not in modes)

    if 'x' in modes:
        data = process_sprite_portraits(data, 'GENERALSTORE' in modes, 'PIXELPARTY' in modes)

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
        
