# the-Floppy-Pinkies

Public transport for the already-filtered Google Sheet live view and real flyer assets.

- `data/live.json` mirrors `ライブスケジュール!A:D`; publication filtering remains owned by the Sheet.
- Future rows with a non-empty `flyerUrl` are mirrored into `img/flyer/`.
- Existing flyer files are retained as the archive.
- `data/media.json` is deterministically rebuilt from valid, date-named image files. A
  `current_event_match` purpose is emitted only when that same published event date has
  its own `flyerUrl`.
