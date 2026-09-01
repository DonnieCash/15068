# 15068

A working **virtual remote control** — a TV remote UI that actually drives an
on-screen TV, running entirely in the browser with no build step or dependencies.

## Run it

Open `index.html` in any browser:

```sh
# just double-click the file, or serve it locally:
npx http-server . -o        # then visit the shown URL
```

## What it does

The remote controls a simulated TV that reflects real state — power, channel,
volume, mute, and input source.

| Control | Action |
| --- | --- |
| **⏻ Power** | Turns the TV on/off (screen fades, standby label) |
| **Number pad + ↵** | Type a channel number, then Enter (auto-commits after ~1.6s) |
| **CH +/−** | Step through named channels |
| **VOL +/−** | Adjust volume with an on-screen bar |
| **🔇 Mute** | Toggle mute |
| **SRC** | Cycle inputs: TV → HDMI 1 → HDMI 2 → AV |
| **D-pad + OK** | Navigation (Up/Down/Left/Right/OK) |
| **MENU / HOME / BACK** | Menu actions |
| **↩ Last** | Jump back to the previous channel |

Named channels include News 2, Sports Central, MovieMax, Prime 7, Discovery+,
Kids Zone, Music Hits, 24h News, Sci-Fi (42), and Retro TV.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `P` | Power |
| `M` | Mute |
| `I` | Input source |
| `↑ ↓ ← →` | Navigation |
| `Enter` | OK / commit channel entry |
| `+` / `−` | Volume up / down |
| `Page Up` / `Page Down` | Channel up / down |
| `0`–`9` then `Enter` | Direct channel entry |

## Files

- `index.html` — the entire app (HTML, CSS, and JS in one self-contained file)
