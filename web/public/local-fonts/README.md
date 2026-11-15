# Local fonts to try out

Everything in this folder except this file is ignored by git: fonts placed here
never reach the repository. The font switch in the footer offers them in
addition to Inter and JetBrains Mono, for the current visit only. If a file is
missing or cannot be loaded, the text falls back to Inter.

1. Copy font files (`.woff2`, `.woff`, `.ttf` or `.otf`) into this folder.
2. Write `fonts.json` next to them:

```json
[
  {
    "name": "IBM Plex Sans",
    "files": [
      { "src": "IBMPlexSans-Regular.woff2", "weight": "400" },
      { "src": "IBMPlexSans-SemiBold.woff2", "weight": "600" },
      { "src": "IBMPlexSans-Bold.woff2", "weight": "700" }
    ]
  },
  { "name": "Atkinson Hyperlegible", "files": [{ "src": "Atkinson.ttf", "weight": "100 900" }] },
  { "name": "Georgia" }
]
```

- `name` is what the switch shows and the family the text is set in.
- `files` lists the files with their weight (`"400"`, or a range such as
  `"100 900"` for a variable font) and optionally `"style": "italic"`.
- Without `files`, the font must be installed on your computer (here: Georgia).

3. Reload the page (in the dev server, or after `npm run build` for the
   walkthrough server). Code stays in JetBrains Mono.

Note: `npm run build` copies this folder into `dist/`. Do not build a release
with fonts in here whose licence does not allow it.
