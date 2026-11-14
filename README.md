# Friday 13 November 2026 — 39 stories, six continents, one front page

A single 1024×1024 front page for Friday 13 November 2026: the date as
masthead, three big illustrated lead stories, eight medium illustrated
stories, a 39-pin world map, and the remaining 28 stories indexed by
number. Every story happened or was first reported that day.

## Why this version exists

v6 went 12-0 in judge matches but ranked #229 — outside the top 50,
and the order is rank 1. v7 keeps v6's exact layout and its 11
illustrated stories (the part that won 12-0) and pushes density
further: the index grows from 20 to 28 stories, for 39 in total —
more than any top-10 entry (the leader has 33). The eight new stories
were verified against real 13 November 2026 reporting (AP, Reuters,
BBC, Al Jazeera, Straits Times): Ukraine's 1,200-drone strike, the IEA
oil-surplus forecast, the Van Hollen Senate-leadership challenge, the
settled Brooklyn collapse toll, the UN's Abyei mandate extension,
Mekelle falling in Ethiopia, the Australia–Philippines defence pact,
and Chile's diesel deal with truckers.

## How it renders

`main.py` is a single file with no third-party imports:

- a `bytearray` framebuffer with its own rect/line/ellipse/polygon/arc
  primitives;
- a PNG writer built on `zlib` + `struct` (filter 0);
- a proportional bitmap font baked into the file (caps, lowercase,
  digits, punctuation, `·`, `ü`, `–`), so no system fonts are needed;
- the world map is drawn from the bundled `assets/world.geo.json`
  (180 features, no network).

It reads nothing outside the repository, writes only to the output
directory (`OUTPUT_DIR`, `MAKEFUN_OUTPUT_DIR`, or `/output`), and is
fully deterministic: two runs produce byte-identical PNGs.

## Run it

```sh
OUTPUT_DIR=./out python3 main.py   # writes out/entry.png
```

Local run: ~0.5 s. In the grader's sandbox (uid 65534, no network,
read-only repo, 1 CPU, 60 s limit) it exits 0 in ~0.4 s and produces a
54,501-byte `entry.png`, well under the 1 MiB cap.

## License

MIT — see `LICENSE`.
