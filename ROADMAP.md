# Roadmap: rhythm-to-mp3

Status: **alpha**. Only tested on one sheet. Reliability comes before new features.
## Done

- [x] Read single-line drum notation from a PNG (note values via beams, stub beams, rests, hand position)
- [x] Read MusicXML and a simple text notation
- [x] Render audio: one count-in, each pattern twice, no gaps
- [x] Optional click track and alternating-hand sounds (`--sticking`)
- [x] Debug overlay image, editable `.txt` and MusicXML export
- [x] BPM in the output filename
- [x] GitHub repo with README, `.gitignore`, requirements

## Phase 1: Convenience (quick wins)

- [ ] **Drag-and-drop `.bat`**: drop one or more PNGs on it, enter a tempo, get MP3 + `_check.png` + `.txt`
- [ ] Add `sheet_to_mp3.bat` to the repo and document it in the README
- [ ] Friendly error messages (missing ffmpeg, missing pillow/numpy, no staff found)
- [ ] `--version` flag and a version number in the README

## Phase 2: Practice features

- [ ] **Tempo ramp**: same sheet at several tempos in one file (e.g. `--ramp 60 90 10`)
- [ ] **Loop one pattern** N times for drilling (`-p 6 -r 16`)
- [ ] **Stereo sticking**: one hand in the left channel, the other in the right
- [ ] Accent and ghost-note volume, so notes are not all equally loud
- [ ] Spoken or click pattern numbers so you know which line is playing
- [ ] Optional count-in between patterns (`--count-in-each`)

## Phase 3: Reliability (the weak point)

- [ ] Collect more test sheets (your own made-up sheets, so no copyright issues) in `examples/`
- [ ] Auto-scale: measure beam thickness and stem length instead of needing `--zoom`
- [ ] Per-measure confidence: flag measures that look suspicious in the overlay
- [ ] Handle dotted notes, triplets, half/whole notes and ties
- [ ] Handle other time signatures (read from the sheet or `--beats`)
- [ ] Tolerate photos and slightly rotated or noisy scans (deskew, threshold tuning)
- [ ] Regression tests: sample image + expected `.txt`, run with `pytest`

## Phase 4: Sound quality and export

- [ ] Real drum samples instead of synthesized snare (royalty-free)
- [ ] MIDI export, to load in a DAW or practice app
- [ ] Choose other sounds (rim click, woodblock, hi-hat)
- [ ] Optional swing/shuffle feel

## Phase 5: Friendlier app (only if the reader proves reliable)

- [ ] Small window: drag-and-drop, tempo slider, pattern picker, Play button
- [ ] Highlight the current note on the sheet while it plays
- [ ] Single `.exe` with PyInstaller, so no Python install is needed
- [ ] Optional: staffed (five-line) notation via an existing OMR tool

## Housekeeping

- [ ] Add a `LICENSE`
- [ ] Split `rhythm_to_mp3.py` into modules (reader, synth, CLI) once it grows
- [ ] GitHub Actions: run tests on each pull request
- [ ] Issue templates asking for a sample sheet when something is misread
- [ ] Tag releases (`v0.1.0`, ...) and write short release notes

## Ideas parking lot

- Web version that runs in the browser
- Print-ready sheet generator from the `.txt` format
- Sticking labels (R/L) written onto the debug overlay
