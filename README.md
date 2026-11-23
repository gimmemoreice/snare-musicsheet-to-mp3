# Snare Music Sheet to MP3

> **Status: alpha.** This tool has not been battle-tested. It was developed and
> checked against a single sheet, so expect misreadings on other layouts, fonts
> and resolutions. Always check the result with `--debug-image` and listen to the
> output before trusting it. Bug reports and sample sheets are welcome.

Turn single-line drum rudiment sheets (PNG) into audio so you can hear the rhythm.
Also reads MusicXML and a simple text notation.

## Install

    pip install -r requirements.txt

For MP3 output install [ffmpeg](https://ffmpeg.org) (Windows: `winget install ffmpeg`).
Without it you get a `.wav`.

## Use

    python rhythm_to_mp3.py sheet.png --click --sticking -t 80

Creates `sheet_80bpm.mp3`: one 4-click count-in, then every pattern twice, back to back.

| Option | Meaning |
|---|---|
| `-t 70` | tempo in BPM (default 80) |
| `-r 4` | repeats per pattern (default 2) |
| `-p 3 6` | only these patterns |
| `--click` | metronome click on every beat |
| `--sticking` | alternate pitch for the two hands |
| `--gap 1` | seconds of silence between patterns |
| `--no-count-in` | skip the count-in |
| `--zoom 2` | rescale the image before reading (small/large scans) |
| `--debug-image check.png` | overlay showing what was detected |
| `--save-txt` / `--save-musicxml` | save the detected rhythm (editable / for MuseScore) |

Check the overlay the first time you use a new sheet. If something was misread,
fix it in the saved `.txt` and run the script on that file instead.

## Supported

Quarter, eighth, sixteenth and 32nd notes (including stub beams); quarter, eighth
and sixteenth rests. Not supported: dotted notes in images, triplets, half/whole
notes, ties. Tuned for clean digital single-line notation of roughly 800 px width.

## Text format

See `examples/example.txt`.
