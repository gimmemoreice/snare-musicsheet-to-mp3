#!/usr/bin/env python3
"""
rhythm_to_mp3.py - turn drum-rudiment rhythm sheets into audio so you can hear them.

Input (by file extension):
  .png .jpg ...                      a sheet image (single-line drum notation, see notes below)
  .musicxml / .xml                   MusicXML (e.g. exported from MuseScore)
  .txt                               simple text notation (see below)

Text notation, one pattern per line, measures separated by |
  1: e e e e e e e e | e e s s s s q rq
  Note values: w h q e s (whole, half, quarter, eighth, sixteenth), add '.' for dotted
  Prefix r for a rest: rq = quarter rest, rs = sixteenth rest.  '#' starts a comment.
  Optional hand marker after a note: ^ = head above the line, _ = head below (used by --sticking).
  A line starting with 'tempo:' or 'time:' is ignored (use -t on the command line).

Image reading (needs: pip install pillow numpy):
  python rhythm_to_mp3.py sheet.png --debug-image check.png --save-txt sheet.txt
  Open check.png to see what was detected; fix mistakes in sheet.txt and re-run on the .txt.
  Supports: quarter/8th/16th/32nd notes (beams, stub beams), 8th/16th/quarter rests.
  Not supported: dotted notes, triplets, half/whole notes, ties. Use --zoom if the image is
  much smaller/larger than ~800 px wide (try --zoom 2 for small images).

Examples:
  python rhythm_to_mp3.py single_stroke_roll_1-8.musicxml
  python rhythm_to_mp3.py sheet.musicxml -t 70 --repeats 4 --click -o practice.mp3
  python rhythm_to_mp3.py sheet.musicxml -p 3 6 --sticking
MP3 encoding needs ffmpeg on PATH (or: pip install lameenc). Otherwise you get a .wav.
"""
import argparse, math, random, shutil, struct, subprocess, sys, wave, os
import xml.etree.ElementTree as ET

SR = 44100
VAL = {'w': 4.0, 'h': 2.0, 'q': 1.0, 'e': 0.5, 's': 0.25, 't': 0.125}   # in quarter-note beats
TYPE = {'whole': 4.0, 'half': 2.0, 'quarter': 1.0, 'eighth': 0.5, '16th': 0.25, '32nd': 0.125}

# ---------- parsing ----------
def parse_text(path):
    pats = []
    for raw in open(path, encoding='utf-8'):
        line = raw.split('#')[0].strip()
        if not line or line.lower().startswith(('tempo:', 'time:')):
            continue
        label, _, body = line.partition(':')
        events = []
        for tok in body.replace('|', ' ').split():
            hand, dotted = None, False
            while tok and tok[-1] in '^_.':
                if tok[-1] == '^': hand = 0
                elif tok[-1] == '_': hand = 1
                else: dotted = True
                tok = tok[:-1]
            rest = tok.startswith('r')
            t = tok[1:] if rest else tok
            if t not in VAL:
                sys.exit(f"Unknown note token '{tok}' in line: {raw.strip()}")
            events.append((rest, VAL[t] * (1.5 if dotted else 1), hand))
        pats.append((label.strip(), events))
    return pats

def strip_ns(root):
    for el in root.iter():
        el.tag = el.tag.split('}')[-1]
    return root

def parse_musicxml(path):
    root = strip_ns(ET.parse(path).getroot())
    pats, cur, label, divisions, idx = [], None, None, 4, 0
    for m in root.iter('measure'):
        for d in m.iter('divisions'):
            divisions = int(d.text)
        fwd = any(b.get('location') == 'left' and b.find('repeat') is not None
                  and b.find('repeat').get('direction') == 'forward' for b in m.findall('barline'))
        back = any(b.find('repeat') is not None and b.find('repeat').get('direction') == 'backward'
                   for b in m.findall('barline'))
        for r in m.iter('rehearsal'):
            label = (r.text or '').strip()
        if fwd or cur is None:
            if cur: pats.append(cur)
            idx += 1
            cur = [label or str(idx), []]
            label = None
        for n in m.findall('note'):
            if n.find('chord') is not None:
                continue
            dur = n.find('duration')
            beats = int(dur.text) / divisions if dur is not None else TYPE.get(n.findtext('type'), 1.0)
            ds = n.findtext('unpitched/display-step')
            cur[1].append((n.find('rest') is not None, beats, {'G': 0, 'C': 1}.get(ds)))
        if back:
            pats.append(cur); cur = None
    if cur: pats.append(cur)
    return [(l, [tuple(x) for x in e]) for l, e in pats if e]


# ---------- image reading ----------
def _runs(mask, gap=0):
    import numpy as np
    xs = np.flatnonzero(mask)
    out = []
    if not len(xs):
        return out
    s = p = int(xs[0])
    for x in xs[1:]:
        x = int(x)
        if x - p > gap + 1:
            out.append((s, p)); s = x
        p = x
    out.append((s, p))
    return out

def _find_systems(dark):
    """Single staff lines: rows holding a long horizontal dark run, 1-3 rows thick."""
    import numpy as np
    H, W = dark.shape
    rows = []
    for y in range(H):
        r = _runs(dark[y])
        if r:
            s, e = max(r, key=lambda t: t[1] - t[0])
            if e - s > 0.4 * W:
                rows.append((y, s, e))
    systems, i = [], 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][0] == rows[j][0] + 1:
            j += 1
        if rows[j][0] - rows[i][0] + 1 <= 3:          # thicker bands are page decoration
            systems.append((rows[i][0], rows[j][0], rows[i][1], rows[i][2]))
        i = j + 1
    return systems

def _parse_system(dark, yt, yb, x0, x1):
    import numpy as np
    H, W = dark.shape
    lo = dark[yb + 8:yb + 14, :].all(axis=0)            # long straight run below = down-stem
    up = dark[yt - 14:yt - 7, :].all(axis=0)            # long straight run above = up-stem
    core = dark[yt - 4:yb + 6, :].all(axis=0)           # dark across the full staff height
    barmask = (core & ~dark[yb + 8] & ~dark[yt - 8]) | (lo & up)   # ...but not continuing as a stem
    lo = lo & ~barmask; up = up & ~barmask
    for m in (lo, up, barmask):
        m[:x0] = False; m[x1 + 1:] = False
    bars = _runs(barmask, 1)
    downs = _runs(lo, 1)
    ups = _runs(up, 1)
    # music zone: skip clef + start-repeat (left) and end-repeat/final bar (right)
    left, right = [], []
    if bars:
        left = [bars[0]]
        for b in bars[1:]:
            if b[0] - left[-1][1] <= 14: left.append(b)
            else: break
        right = [bars[-1]]
        for b in reversed(bars[:-1]):
            if right[0][0] - b[1] <= 14: right.insert(0, b)
            else: break
        if set(left) & set(right):
            right = []
    mstart = left[-1][1] + 8 if left else x0
    mend = right[0][0] - 8 if right else x1
    interior = [b for b in bars if b not in left and b not in right]
    events = []
    acc = {1: [], -1: []}
    # --- notes ---
    for stems, direction in ((downs, 1), (ups, -1)):
        for s, e in stems:
            c = (s + e) // 2
            if not (mstart - 4 <= c <= mend + 4):
                continue
            y = (yb + 8) if direction == 1 else (yt - 8)
            while 0 < y + direction < H and dark[y + direction, c]:
                y += direction
            nb = 0
            for k in range(4):
                row = y - direction * (1 + 4 * k)
                if 0 <= row < H and (dark[row, max(0, c - 4):c - 2].any() or dark[row, c + 3:c + 5].any()):
                    nb += 1
                else:
                    break
            dur = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.125}[nb]
            # head above or below the line?
            hx0, hx1 = (c + 2, c + 10) if direction == 1 else (c - 9, c - 1)
            above = int(dark[max(0, yt - 6):yt, hx0:hx1].sum())
            below = int(dark[yb + 1:yb + 7, hx0:hx1].sum())
            if max(above, below) < 12:        # no notehead -> not a note (e.g. a rest's stroke)
                continue
            acc[direction].append((s, e))
            events.append(dict(x=c, kind='n', dur=dur, hand=0 if above > below else 1,
                               y=y, nb=nb, dir=direction))
    # --- rests: ink not explained by stems/heads/bars ---
    top, bot = yt - 14, yb + 9
    ink = dark[top:bot + 1, :].copy()
    for r in range(yt - top, yb - top + 1):
        ink[r, :] = False                               # drop the staff line itself
    col = ink.any(axis=0)
    col[:mstart] = False; col[mend + 1:] = False
    for s, e in acc[1]: col[max(0, s - 3):e + 11] = False
    for s, e in acc[-1]: col[max(0, s - 11):e + 4] = False
    for s, e in bars: col[max(0, s - 3):e + 4] = False
    for s, e in _runs(col, 2):
        rr = np.flatnonzero(ink[:, s:e + 1].any(axis=1))
        h, w = int(rr.max() - rr.min() + 1), e - s + 1
        if h >= 9 and w >= 4:
            above_ext, below_ext = yt - (top + int(rr.min())), (top + int(rr.max())) - yb
            if above_ext <= 10: dur = 0.5                     # eighth rest: short
            elif below_ext >= 3: dur = 1.0                    # quarter rest: long tail under the line
            else: dur = 0.25                                  # sixteenth rest: tall, short tail
            events.append(dict(x=(s + e) // 2, kind='r', dur=dur, hand=None, y=top + int(rr.min()), h=h))
    events.sort(key=lambda ev: ev['x'])
    cuts = sorted((b[0] + b[1]) / 2 for b in interior)
    measures = [[] for _ in range(len(cuts) + 1)]
    for ev in events:
        measures[sum(ev['x'] > c for c in cuts)].append(ev)
    return measures, bars, mstart, mend

def read_image(path, zoom=1.0, debug_path=None, beats=4.0):
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except ImportError:
        sys.exit('Image input needs:  pip install pillow numpy')
    im = Image.open(path).convert('L')
    if zoom != 1.0:
        im = im.resize((int(im.width * zoom), int(im.height * zoom)), Image.LANCZOS)
    dark = np.array(im) < 120
    systems = _find_systems(dark)
    if not systems:
        sys.exit('No staff lines found in the image.')
    dbg = Image.merge('RGB', (im, im, im)) if debug_path else None
    d = ImageDraw.Draw(dbg) if dbg else None
    sym = {1.0: 'q', 0.5: 'e', 0.25: 's', 0.125: 't'}
    pats = []
    for n, (yt, yb, x0, x1) in enumerate(systems, 1):
        measures, bars, mstart, mend = _parse_system(dark, yt, yb, x0, x1)
        events = []
        for mi, m in enumerate(measures, 1):
            tot = sum(ev['dur'] for ev in m)
            if abs(tot - beats) > 1e-6:
                print(f'  WARNING: pattern {n}, measure {mi} adds up to {tot:g} beats (expected {beats:g}) - check this one')
            events.append(m)
        if d:
            for b in bars: d.line([(b[0], yt - 14), (b[0], yb + 14)], fill=(0, 120, 255))
            for m in events:
                for ev in m:
                    if ev['kind'] == 'n':
                        d.text((ev['x'] - 3, yb + 24), sym[ev['dur']], fill=(220, 0, 0))
                        d.text((ev['x'] - 3, yt - 24), '^' if ev['hand'] == 0 else '_', fill=(0, 150, 0))
                    else:
                        d.rectangle([ev['x'] - 6, ev['y'] - 2, ev['x'] + 6, ev['y'] + ev['h'] + 2], outline=(220, 0, 0))
                        d.text((ev['x'] - 3, yb + 24), 'r' + sym[ev['dur']], fill=(220, 0, 0))
            d.text((max(2, x0 - 60), yt - 6), f'#{n}', fill=(0, 0, 200))
        flat = []
        for m in events:
            flat.extend((ev['kind'] == 'r', ev['dur'], ev['hand']) for ev in m)
        pats.append((str(n), flat, [len(m) for m in events]))
    if dbg:
        dbg.save(debug_path)
        print('Wrote debug overlay:', debug_path, '(red = detected durations, ^/_ = head above/below, blue = barlines)')
    return pats

def pats_to_text(pats, beats=4.0):
    sym = {1.0: 'q', 0.5: 'e', 0.25: 's', 0.125: 't'}
    lines = ['# generated from an image - check against the sheet; ^ head above line, _ head below']
    for label, events, counts in pats:
        parts, i = [], 0
        for c in counts:
            toks = []
            for rest, d, h in events[i:i + c]:
                toks.append(('r' if rest else '') + sym.get(d, 'q') + ({0: '^', 1: '_'}.get(h, '') if not rest else ''))
            parts.append(' '.join(toks)); i += c
        lines.append(f'{label}: ' + ' | '.join(parts))
    return '\n'.join(lines) + '\n'

def pats_to_musicxml(pats, path):
    T = {1.0: ('quarter', 4), 0.5: ('eighth', 2), 0.25: ('16th', 1), 0.125: ('32nd', 0.5)}
    out = ['<?xml version="1.0" encoding="UTF-8"?><score-partwise version="3.1"><part-list><score-part id="P1">'
           '<part-name>Rhythm</part-name></score-part></part-list><part id="P1">']
    mn = 0
    for label, events, counts in pats:
        i = 0
        for k, c in enumerate(counts):
            mn += 1
            s = f'<measure number="{mn}">'
            if k == 0:
                s += '<print new-system="yes"/>'
                if mn == 1:
                    s += ('<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time>'
                          '<clef><sign>percussion</sign></clef><staff-details><staff-lines>1</staff-lines></staff-details></attributes>')
                s += f'<direction placement="above"><direction-type><rehearsal>{label}</rehearsal></direction-type></direction>'
                s += '<barline location="left"><repeat direction="forward"/></barline>'
            for rest, d, h in events[i:i + c]:
                ty, du = T.get(d, T[1.0])
                if rest:
                    s += f'<note><rest/><duration>{du:g}</duration><voice>1</voice><type>{ty}</type></note>'
                else:
                    step = 'G' if h == 0 else 'C'
                    s += (f'<note><unpitched><display-step>{step}</display-step><display-octave>4</display-octave></unpitched>'
                          f'<duration>{du:g}</duration><voice>1</voice><type>{ty}</type><stem>down</stem></note>')
            i += c
            if k == len(counts) - 1:
                s += '<barline location="right"><repeat direction="backward"/></barline>'
            out.append(s + '</measure>')
    out.append('</part></score-partwise>')
    open(path, 'w', encoding='utf-8').write(''.join(out))

# ---------- synthesis ----------
def snare(gain=1.0, pitch=190.0):
    n = int(SR * 0.14)
    out = []
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 38)
        tone = math.sin(2 * math.pi * pitch * t) * math.exp(-t * 55) * 0.5
        out.append((random.uniform(-1, 1) * 0.7 * env + tone) * gain)
    return out

def click(accent=False):
    f = 1600 if accent else 1100
    n = int(SR * 0.03)
    return [math.sin(2 * math.pi * f * i / SR) * math.exp(-i / SR * 120) * 0.35 for i in range(n)]

def render(patterns, bpm, repeats, count_in, use_click, sticking, gap):
    spb = 60.0 / bpm
    segs = []   # list of (start_seconds, samples)
    t = 0.0
    if count_in:                      # one count-in at the very start only
        for k in range(4):
            segs.append((t + k * spb, click(k == 0)))
        t += 4 * spb
    for label, events in patterns:
        total = sum(e[1] for e in events)
        for rep in range(repeats):
            pos, hand = 0.0, 0
            for rest, d, h in events:
                if not rest:
                    if sticking:
                        hh = h if h is not None else hand
                        segs.append((t + pos * spb, snare(1.0 if hh == 0 else 0.8, 190 if hh == 0 else 165)))
                        hand ^= 1
                    else:
                        segs.append((t + pos * spb, snare()))
                pos += d
            if use_click:
                for b in range(int(math.ceil(total))):
                    segs.append((t + b * spb, click(b % 4 == 0)))
            t += total * spb
        t += gap
    n = int((t + 0.5) * SR)
    buf = [0.0] * n
    for start, s in segs:
        i0 = int(start * SR)
        for j, v in enumerate(s):
            if i0 + j < n:
                buf[i0 + j] += v
    peak = max(1e-9, max(abs(x) for x in buf))
    return [x / peak * 0.9 for x in buf]

# ---------- output ----------
def write_wav(path, samples):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, x)) * 32767)) for x in samples))

def to_mp3(wav, mp3):
    ff = shutil.which('ffmpeg')
    if ff:
        subprocess.run([ff, '-y', '-loglevel', 'error', '-i', wav, '-codec:a', 'libmp3lame', '-q:a', '2', mp3], check=True)
        return True
    try:
        import lameenc
        with wave.open(wav) as w:
            pcm = w.readframes(w.getnframes())
        enc = lameenc.Encoder(); enc.set_bit_rate(192); enc.set_in_sample_rate(SR)
        enc.set_channels(1); enc.set_quality(2)
        open(mp3, 'wb').write(enc.encode(pcm) + enc.flush())
        return True
    except ImportError:
        return False

def main():
    ap = argparse.ArgumentParser(description='Rhythm sheet -> audio', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('input')
    ap.add_argument('-o', '--output', help='output file (.mp3 or .wav)')
    ap.add_argument('-t', '--tempo', type=float, default=80, help='quarter-note BPM (default 80)')
    ap.add_argument('-r', '--repeats', type=int, default=2, help='times each pattern is played (default 2)')
    ap.add_argument('-p', '--patterns', nargs='*', help='only these pattern labels, e.g. -p 1 3 5')
    ap.add_argument('--click', action='store_true', help='add a metronome click on every beat')
    ap.add_argument('--sticking', action='store_true', help='alternate pitch/volume to hear R/L hands')
    ap.add_argument('--no-count-in', action='store_true', help='skip the 4-click count-in at the start')
    ap.add_argument('--zoom', type=float, default=1.0, help='rescale image before reading (try 2 for small images)')
    ap.add_argument('--beats', type=float, default=4.0, help='quarter-note beats per measure, for sanity checks (default 4)')
    ap.add_argument('--debug-image', help='(image input) write an overlay PNG showing what was detected')
    ap.add_argument('--save-txt', help='(image input) save the detected rhythm as editable text')
    ap.add_argument('--save-musicxml', help='(image input) save the detected rhythm as MusicXML for MuseScore')
    ap.add_argument('--gap', type=float, default=0.0, help='seconds of silence between patterns (default 0 = continuous)')
    a = ap.parse_args()

    ext = os.path.splitext(a.input)[1].lower()
    if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff'):
        raw = read_image(a.input, a.zoom, a.debug_image, a.beats)
        if a.save_txt:
            open(a.save_txt, 'w', encoding='utf-8').write(pats_to_text(raw)); print('Wrote', a.save_txt)
        if a.save_musicxml:
            pats_to_musicxml(raw, a.save_musicxml); print('Wrote', a.save_musicxml)
        pats = [(l, e) for l, e, _ in raw]
    elif ext == '.txt':
        pats = parse_text(a.input)
    else:
        pats = parse_musicxml(a.input)
    if a.patterns:
        pats = [p for p in pats if p[0] in a.patterns]
    if not pats:
        sys.exit('No patterns found (check the file, or your -p selection).')
    print(f'Found {len(pats)} pattern(s): ' + ', '.join(p[0] for p in pats))

    audio = render(pats, a.tempo, a.repeats, not a.no_count_in, a.click, a.sticking, a.gap)
    bpm_txt = f'{a.tempo:g}'
    out = a.output or f'{os.path.splitext(a.input)[0]}_{bpm_txt}bpm.mp3'
    wav = os.path.splitext(out)[0] + '.wav'
    write_wav(wav, audio)
    if out.lower().endswith('.mp3'):
        if to_mp3(wav, out):
            os.remove(wav); print('Wrote', out)
        else:
            print('No MP3 encoder found (install ffmpeg, or: pip install lameenc).')
            print('Wrote WAV instead:', wav)
    else:
        print('Wrote', wav)

if __name__ == '__main__':
    main()
