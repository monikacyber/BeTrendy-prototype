# BeTrendy draft importer

This plugin only operates when both the runtime home URL and the stored home URL
use `betrendy.online` or its exact Hostinger alias `snow-anteater-890728.hostingersite.com`.
Activate WooCommerce and **BeTrendy Source URLs** first. Set `import-config.json`
`github_commit` to the full immutable 40-character commit of the verified GitHub
media archive and re-run the packaging script. Optional installed media data packs
`betrendy-media-1` through `betrendy-media-4` are used first when present.

Activation queues a resumable import. Each batch processes at most four media files
or two category, product or page records, with a 12-second time budget checked
between records. All 61 Ukrainian products and eight Ukrainian
pages/posts remain drafts. RU/EN records are preserved as translation data, not
published storefronts. Only media referenced by the Ukrainian content are imported.
Media are copied from local packs, or fetched from the exact `raw.githubusercontent.com`
repository/commit/path after SHA-256 verification. Redirects are disabled. The
importer never downloads replacements from the live source site.

The store currency can change to UAH only when the store contains **zero products**,
including trash. An existing store using another currency pauses before importing.
Unrelated existing SKUs, categories, pages, attachments and source routes are never
overwritten. Deactivation clears scheduled importer events. Reactivation does not
automatically restart a paused or completed import.

Administrators can inspect the private `betrendy_import` post type through the
WordPress connector (`content_types_get`, then `content_items_list`, with private
status and edit context). Anonymous REST access to its route is explicitly denied.
The status record's content contains JSON progress and any pause reason.

Update that record's registered REST meta `betrendy_import_command`:

- `run`: process one bounded batch immediately (also schedules the next cron batch).
- `pause`: pause and clear scheduled events.
- `resume`: clear the pause and attempt one batch from the saved checkpoint.
- `verify`: after completion, compare real products, prices, images, categories and
  page block counts with the snapshot. Updates only the private verification report.
- `verify_published`: the same read-only comparison, expecting published products
  and pages/posts. Its report is saved separately as `verification_published`.
- `archive_media`: after the original import completes, start or resume a separate
  queue for **all 389 manifest images**. Existing attachments are reused, and their
  original files are checked against SHA-256; no products or pages are changed.
  `run` continues this queue, and `pause` / `resume` control it while the original
  import remains complete. The private `media_archive` report records progress,
  created/reused files and verified checksums. Each batch downloads at most four
  files and examines at most 24 records within a 12-second budget between files.

Only an administrator can issue these commands; they affect only the unique status
record created by this plugin. A completed job cannot be restarted by these commands.
Each media attachment and imported record is checkpointed, so retries reuse their
source identifiers. A fatal PHP error pauses the job; inspect server logs and resume.

The archive queue has its own persisted checkpoint and never resets the original
import STATE, attachment mapping or completed content. A changed manifest or
missing/changed original attachment pauses the archive instead of replacing files.
The normal verification commands check the 246 images referenced by Ukrainian
content; the separate archive report covers all 389 original files.

The importer does not publish content, configure checkout, payment gateways,
multilingual display, DNS or the front page. Review and configure these separately.

Packaging: `python3 betrendy/scripts/package-import-plugin.py`. The deployment payload
uses guarded PHP files whose direct HTTP requests return404, and a guarded checksum
manifest. No raw source JSON is installed under `data/`. Apache/LiteSpeed access is
also denied by `.htaccess`. The generated `data/` directory is excluded from the
public GitHub export; rebuild it from the repository's root snapshot JSON when needed.
The local deployment ZIP may contain the full source snapshot; do not publish that
ZIP in a public repository. Public repository builds use the redacted root snapshot.

API references: [post-type REST completion hook](https://developer.wordpress.org/reference/hooks/rest_after_insert_this-post_type/),
[registered REST meta](https://developer.wordpress.org/reference/functions/register_post_meta/),
[single cron events](https://developer.wordpress.org/reference/functions/wp_schedule_single_event/).
