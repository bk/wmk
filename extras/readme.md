# Extras

This directory is for scripts or other extra material that can be generally
useful for wmk sites.

## Import from WordPress

The script `wordpress2content.py` uses the WordPress REST API to get posts and
pages from a WordPress site and export them as content files in `content/`.
Images and other media files from the origin's `wp-content/uploads/` folder go
into `static/_fetched/`.

This may either be used to migrate from WordPress to a static site maintained
by wmk, or to use a (possibly non-public) WordPress installation as a headless
CMS for external authors or non-technical users.

For the latter task, the helper scripts `duplicate_wp_content.py` and
`removed_wp_content.py` may help with the housekeeping involved in keeping the
content properly synchronized.

### Usage

```
wordpress2content.py [basedir] [url|json_file|json_literal]
```

- `basedir`: Base directory for the wmk project. By default '.' (i.e. the
  current working directory).
  
- `url`: The URL of the WordPress site for fetching data from.  Without a
  trailing slash. Default: `http://localhost`. The REST endpoint
  `/?rest_route=/wp/v2/` will be appended automatically.

- `json_file`: A JSON file with further settings. Needed if you want to
  specify other things than just the source URL, e.g. how many posts/pages
  per page of JSON results or whether to stop after at most some number of
  JSON pages fetched, or what content_prefix subdirectory to use.

- `json_literal`: A string containing the JSON to use as settings, in the
  same format as the contents of the `json_file`.

The script will detect automatically which of `url`, `json_file` or
`json_literal` is being specified. The `basedir` must contain the folders
`content/`, `static/` and `data/`.

The settings are a JSON object. The following keys are supported:

- `url` - default `http://localhost`.
- `content_types` - list of content types to fetch. Currently only the core
  types `posts` and `pages` are supported. Default value: `["posts", "pages"]`.
- `per_page` - how many items per page of results. Default 10, max 100.
- `max_pages` - how many pages of results to fetch at most for each content
  type. Default: 10000.
- `get_images` - whether to download images from the WordPress site into
  `static/`. Default: true.
- `content_prefix` - directory name inside `content/` and `static/_fetched/` for
  the content and images being fetched. This allows fetching data from more than
  one WordPress site. Default: `from-wp`.
- `posts_dir` - subdirectory for posts. Default: `posts`.
- `pages_dir` - subdirectory for pages. Default: `pages`.

Last-modified time for each WordPress site that has been fetched from is kept in
the JSON file `data/wordpress2content-refdate.json`, which must be edited or
removed if you wish to refetch everything. Content files will not be overwritten
unless the source has been modified more recently than the saved timestamp.
Static files will not be refetched, regardless of the timestamp.

### Helper scripts

Note that renames and deletions of posts or pages at the origin are not detected
by `wordpress2content.py`, so repeated invocations over an extended period may
cause duplicated or stale content in the wmk content directory relative to the
WordPress source site.

Renames can be detected by looking for duplicated `external_id` values in the
frontmatter of the content items inside the import directory, whereupon the item
or items with the earlier `modified_date` can be removed. The auxiliary script
`duplicate_wp_content.py` helps with this task.

Detecting content that has been deleted or otherwise deactivated, however,
requires comparing with the WordPress API directly for each item imported in
earlier runs. This is what the auxiliary script `removed_wp_content.py` does.

Both of these scripts only list the duplicates/deletions for you. The relevant
content files will still have to be removed manually.
