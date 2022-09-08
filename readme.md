# wmk

wmk is a flexible and versatile static site generator written in Python.

<!-- features "Main features" 10 -->

## Main features

The following features are present in several static site generators (SSGs); you
might almost call them standard:

- Markdown content with YAML metadata in the frontmatter.
- Support for themes.
- Sass/SCSS support (via [`libsass`][libsass]).
- Can generate a search index for use by [`lunr.js`][lunr].
- Shortcodes for more expressive and extensible Markdown content.

The following features are among the ones that set wmk apart:

- The content is rendered using [Mako][mako], a template system which makes all
  the resources of Python easily available to you.
- "Stand-alone" templates – i.e. templates that are not used for presenting
  Markdown-based content – are also rendered if present.
- Additional data for the site may be loaded from separate YAML files ­ or even
  (with a small amount of Python/Mako code) from other data sources such as CSV
  files, SQL databases or REST/graphql APIs.
- The shortcode system is considerably more powerful than that of most static
  site generators. For instance, among the default shortcodes are an image
  thumbnailer and a page list component. A shortcode is just a Mako component,
  so if you know some Python you can easily build your own.
- Optional support for the powerful [Pandoc][pandoc] document converter, for the
  entire site or on a page-by-page basis. This gives you access to such features
  as LaTeX math markup and academic citations, as well as to Pandoc's
  well-designed filter system for extending Markdown.

The only major feature that wmk is missing compared to some other SSGs is tight
integration with a Javascript assets pipeline and interaction layer. Thus, if
your site is reliant upon React, Vue or similar, then wmk is probably not the
best way to go.

That exception aside, wmk is suitable for building any small or medium-sized
static website (up to a few hundred pages).

[libsass]: https://sass.github.io/libsass-python/
[lunr]: https://lunrjs.com/
[mako]: https://www.makotemplates.org/
[pandoc]: https://pandoc.org/

<!-- installation "Installation" 20 -->

## Installation

### Method 1: git + pip

Clone this repo into your chosen location (`$myrepo`) and install the necessary
Python modules into a virtual environment:

```shell
cd $myrepo
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

After that, either put `$myrepo/bin` into your `$PATH` or create a symlink from
somewhere in your `$PATH` to `$myrepo/bin/wmk`.

Required software (aside from Python, of course):

- `rsync` (for static file copying).
- For `wmk watch` functionality (as well as `watch-serve`), you need either
  `inotifywait` or `fswatch` to be installed and in your `$PATH`. If both are
  available, the former is preferred.

wmk requires a Unix-like environment. In particular, bash must be installed
in `/bin/bash`, and the directory separator is assumed to be `/`.

### Method 2: Homebrew

If you are on MacOS and already have Homebrew, this is the easiest installation
method.

First add the tap to your repositories:

```shell
brew tap bk/wmk
```

Then install wmk from it:

```
brew install --build-from-source wmk
```

### Method 3: Docker

If you are neither on a modern Linux system nor on MacOS with Homebrew, it may
be a better option for you to run wmk via Docker. In that case, after cloning
the repo (or simply copying the `Dockerfile` from it) you can give the command

```shell
docker build -t wmk .
```

in the directory containing the `Dockerfile`, in order to build an image called
`wmk`. You can then run the various wmk subcommands via Docker, for instance

```shell
docker run --rm --volume $(pwd):/data --user $(id -u):$(id -g) wmk b .
```

to build the wmk project in the current directory, or

```shell
docker run --rm -i -t --volume $(pwd):/data --user $(id -u):$(id -g) -p 7007:7007 wmk ws . -i 0.0.0.0
```

to watch for changes in the current directory and run a webserver for the built
files.

Obviously, such commands can be unwieldy, so if you run them regularly you may
want to create aliases or wrappers for them.

<!-- usage "Usage: The wmk command" 30 -->

## Usage

The `wmk` command structure is `wmk <action> <base_directory>`. The base
directory is of course the directory containing the source files in
subdirectories such as `templates`, `content`, etc.  Also
see the "File organization" section below.

- `wmk info $basedir`: Shows the real path to the location of `wmk.py` and of
  the content base directory. E.g. `wmk info .`. Synonyms for `info` are `env`
  and `debug`.

- `wmk init $basedir`: In a folder which contains `content/` (with Markdown
  files) but no `wmk_config.yaml`, creates some initial templates as well
  as a sample `wmk_config.yaml`, thus making it quicker for you to start a new
  project.

- `wmk build $basedir [-q|--quick]`: Compiles/copies files into `$basedir/htdocs`.
  If `-q` or `--quick` is specified as the third argument, only files considered to
  have changed, based on timestamp checking, are processed. Synonyms for `run` are
  `run`, `b` and `r`.

- `wmk watch $basedir`: Watches for changes in the source directories inside
  `$basedir` and recompiles if changes are detected. (Note that `build` is not
  performed automatically before setting up file wathcing, so you may want to
  run that first). A synonym for `watch` is `w`.

- `wmk serve $basedir [-p|--port <portnum>] [-i|--ip <ip-addr>]`: Serves the
  files in `$basedir/htdocs` on `http://127.0.0.1:7007/` by default. The IP and
  port can be modified with the `-p` and `-i` switches or be be configured via
  `wmk_config.yaml` – see the "Configuration file" section). Synonyms for
  `serve` are `srv` and `s`.

- `wmk watch-serve $basedir [-p|--port <portnum>] [-i|--ip <ip-addr>]`: Combines
  `watch` and `serve` in one command. Synonym: `ws`.

- `wmk clear-cache $basedir`: Remove the HTML rendering cache, which is a SQLite
  file in `$basedir/tmp/`. This should only be necessary in case of changed
  shortcodes or shortcode dependencies. Note that the cache can be disabled in
  `wmk_config.yaml` by setting `use_cache` to `false`, or on file-by-file basis
  via a frontmatter setting (`no_cache`). A synonym for `clear-cache` is `c`.

<!-- organization "File organization" 40 -->

## File organization

Inside a given working directory, `wmk` assumes the following subdirectories for
content and output. They will be created if they do not exist:

- `htdocs`: The output directory. Rendered, processed or copied content is
  placed here, and `wmk serve` will serve files from this directory.

- `templates`: Mako templates. Templates with the extension `.mhtml` are
  rendered directly into `htdocs` as `.html` files (or another extension if the
  filename ends with `.$ext\.mhtml`, where `$ext` is a string consisting of 2-4
  alphanumeric characters), unless their filename starts with a dot or
  underscore or contains the string `base`, or if they are directly inside a
  subdirectory named `base`. For details on context variables received by such
  stand-alone templates, see the "Context variables" section below.

- `content`: Markdown content with YAML metadata. This will be rendered into
  html using the `template` specified in the metadata or `md_base.mhtml` by
  default. The target filename will be `index.html` in a directory corresponding
  to the basename of the markdown file, unless `pretty_path` in the metadata is
  `false` or the name of the Markdown file itself is `index.md` (in which case
  only the extension is replaced). The converted content will be passed to the
  Mako template as a string in the context variable `CONTENT`, along with other
  metadata. A YAML datasource can be specified in the metadata block as `LOAD`;
  the data in this file will be added to the context. For further details on the
  context variables, see the "Context variables" section. Files that have other
  extensions than `.md` or `.yaml` will be copied directly over to the
  (appropriate subdirectory of the) `htdocs` directory. This is so as to enable
  "bundling", i.e. keeping images together with related markdown files.

- `data`: YAML files for additional metadata.

- `py`: Directory for Python files. This directory is automatically added to the
  front of `sys.path` before Mako is initialized, meaning that Mako templates
  can import modules placed here. Implicit imports are possible by setting
  `mako_imports` in the config file (see the "Configuration file" section).
  There are also two special files that may be placed here: `wmk_autolaod.py` in
  your project, and `wmk_theme_autoload.py` in the theme's `py/` directory.  If
  one or both of these is present, wmk imports a dict named `autoload` from
  them. This means that you can assign `PREPROCESS` and `POSTPROCESS` page
  actions by name (i.e. keys in the `autoload` dict) rather than as function
  references, which in turn makes it possible to specify them in the frontmatter
  directly rather than having to do it via a shortcode. (For more on `PRE-` and
  `POSTPROCESS`, see the "Site and page variables" section).

- `assets`: Assets for an asset pipeline. Currently this only handles SCSS/Sass
  files in the subdirectory `scss`. They will be compiled to CSS which is placed
  in the target directory `htdocs/css`.

- `static`: Static files. Everything in here will be rsynced directoy over to
  `htdocs`.

<!-- gotchas "A few gotchas" 50 -->

## A few gotchas

The following are some of the things you might find surprising when creating a
website with wmk:

* The order of operations is as follows: (1) Copy files from `static/`; (2) run
  asset pipeline; (3) render Mako templates from `templates`; (4) render
  Markdown content from `content`. As a consequence, later steps **may
  overwrite** files placed by earlier steps. This is intentional but definitely
  something to keep in mind.

* For the `run` and `watch` actions when `-q` or `--quick` is specified as a
  modifier, `wmk.py` uses timestamps to prevent unnecessary re-rendering of
  templates, markdown files and SCSS sources. The check is rather primitive and
  does not take account of such things as shortcodes or changed dependencies
  in the template chain. As a rule, `--quick` is therefore **not recommended**
  unless you are working on a small, self-contained set of Markdown files.

* If templates or shortcodes have been changed it may sometimes be necessary to
  clear out the page rendering cache with `wmc c`. During development you may
  want to add `use_cache: no` to the `wmk_config.yaml` file. Also, some pages
  should never be cached, in which case it is a good idea to add `no_cache: true`
  to their frontmatter.

* If files are removed from source directories the corresponding files in
  `htdocs/` **will not disappear** automatically. You have to clear them out
  manually – or simply remove the entire directory and regenerate.

<!-- vars "Context variables" 60 -->

## Context variables

The Mako templates, whether they are stand-alone or being used to render
Markdown content, receive the following context variables:

- `DATADIR`: The full path to the `data` directory.
- `WEBROOT`: The full path to the `htdocs` directory.
- `CONTENTDIR`: The full path to the `content` directory.
- `TEMPLATES`: A list of all templates which will potentially be rendered
  as stand-alone. Each item in the list contains the keys `src` (relative path
  to the source template), `src_path` (full path to the source template),
  `target` (full path of the file to be written), and `url` (relative url to the
  file to be written).
- `MDCONTENT`: An `MDContentList` representing all the markdown files which will
  potentially be rendered by a template. Each item in the list contains the keys
  `source_file`, `source_file_short` (truncated and full paths to the source),
  `target` (html file to be written), `template` (filename of the template which
  will be used for rendering), `data` (most of the context variables seen by
  this content), `doc` (the raw markdown source), and `url` (the `SELF_URL`
  value for this content – see below). If the configuration setting `pre_render`
  is True, then `rendered` (the HTML produced by converting the markdown) is
  present as well. Note that `MDCONTENT` is not available inside shortcodes.
  An `MDContentList` is a list object with some convenience methods for
  filtering and sorting. It is described at the end of this Readme file.
- Whatever is defined under `template_context` in the `wmk_config.yaml` file
  (see the "Configuration file" section below).
- `SELF_URL`: The relative path to the HTML file which the output of the
  template will be written to.
- `SELF_TEMPLATE`: The path to the current template file (from the template
  root).
- `site`: A dict-like object containing the variables specified under the `site`
  key in `wmk_config.yaml`.

When templates are rendering Markdown content, they additionally get the
following context variables:

- `CONTENT`: The rendered HTML produced from the markdown source.
- `RAW_CONTENT`: The original markdown source.
- `SELF_FULL_PATH`: The full path to the source Markdown file.
- `MTIME`: A datetime object representing the modification time for the markdown
  file.
- `DATE`: A datetime object representing the first found value of `date`,
  `pubdate`, `modified_date`, `expire_date`, or `created_date` found in the YAML
  front matter, or the `MTIME` value as a fallback. Since this is guaranteed to
  be present, it is natural to use it for sorting and generic display purposes.
- `RENDERER`: A callable which enables a template to render markdown in `wmk`'s
  own environment. This is mainly so that it is possible to support shortcodes
  which depend on other markdown content which itself may contain shortcodes.
  The callable receives a dict containing the keys `doc` (the markdown) and
  `data` (the context variables) and returns rendered HTML.
- `page`: A dict-like object containing the variables defined in the YAML meta
  section at the top of the markdown file, in `index.yaml` files in the markdown
  file directory and its parent directories inside `content`, and possibly in
  YAML files from the `data` directory loaded via the `LOAD` directive in the
  metadata.

For further details on context variables set in the markdown frontmatter and in
`index.yaml` files, see the "Site and page variables" section below.

<!-- config "Configuration file" 70 -->

## Configuration file

A config file, `$basedir/wmk_config.yaml`, can be used to configure some aspects
of how `wmk` operates. The name of the file may be changed by setting the
environment variable `WMK_CONFIG` which should contain a filename without a
leading directory path.

The configuration file **must** exist (but may be empty). Currently there is
support for the following settings:

- `template_context`: Default values for the context passed to Mako templates.
  This should be a dict.

- `site`: Values for common information relating to the website. These are also
  added to the template context under the key `site`. Also
  see the "Site and page variables" section below.

- `render_drafts`: Normally, markdown files with `draft` set to a true value in
  the metadata section will be skipped during rendering. This can be turned off
  (so that the `draft` status flag is ignored) by setting `render_drafts` to True
  in the config file.

- `markdown_extensions`: A list of [extensions][ext] to enable for markdown
  processing by Python-Markdown. The default is `['extra', 'sane_lists']`.
  If you specify [third-party extensions][other] here, you have to install them
  into the Python virtual environment first. Obviously, this has no effect
  if `pandoc` is true. May be set or overridden through frontmatter variables.

- `markdown_extension_configs`: Settings for your markdown extensions. May be
  set in the config file or in the frontmatter. For convenience, there are
  special frontmatter settings for two extensions, namely for `toc` and
  `wikilinks`:
  - The `toc` boolean setting will turn the `toc` extension off if set to False
    and on if set to True, regardless of its presence in `markdown_extensions`.
  - If `toc` is in `markdown_extensions` (or has been turned on via the `toc`
    boolean), then the `toc_depth` frontmatter variable will affect the
    configuration  of the extension regardless of the `markdown_extension_configs`
    setting.
  - If `wikilinks` is in `markdown_extensions` then the options specified
    in the `wikilinks` frontmatter setting will be passed on to the extension.
    Example: `wikilinks: {'base_url': '/somewhere'}`.

- `pandoc`: Normally [Python-Markdown][pymarkdown] is used for Markdown
  processing, but if this boolean setting is true, then Pandoc via
  [Pypandoc][pypandoc] is used by default instead. This can be turned off or on
  through frontmatter variables as well.

- `pandoc_filters`, `pandoc_options`: Lists of filters and options for Pandoc.
  Has no effect unless `pandoc` is true. May be set or overridden through
  frontmatter variables.

- `pandoc_input_format`, `pandoc_output_format`: Which input and output formats
  to assume for Pandoc. The defaults are `markdown` and `html`, respectively.
  For the former the value should be a markdown subvariant, i.e. one of
  `markdown` (pandoc-flavoured), `gfm` (github-flavoured), `markdown_mmd`
  (MultiMarkdown), `markdown_phpextra`, or `markdown_strict`. For the latter,
  it should be an HTML variant, i.e. either `html`, `html5` or `html4`, or
  alternatively one of the HTML-based slide formats, i.e. `s5`, `slideous`,
  `slidy`, `dzslides` or `reavealjs`.  These options have no effect unless
  `pandoc` is true; both may be overridden through frontmatter variables.

- `use_cache`: boolean, True by default. If you set this to False, the Markdown
  rendering cache will be disabled. This is useful for small and medium-sized
  projects where the final HTML output often depends on factors other than the
  Markdown files themselves. Note that caching for a specific file can be turned
  off by putting `no_cache: true` in the frontmatter.

- `sass_output_style`: The output style for Sass/SCSS rendering. This should be
  one of `compact`, `compressed`, `expanded` or `nested`. The default is
  `expanded`.

- `lunr_index`: If this is True, a search index for `lunr.js` is written as a
  file named `idx.json` in the root of the `htdocs/` directory. Basic
  information about each page (title and summary) is additionally written to
  `idx.summaries.json`.

- `lunr_index_fields`: The default fields for generating the lunr search index
  are `title` and `body`. Additional fields and their weight can be configured
  through this variable. For instance `{"title": 10, "tags": 5, "body": 1}`.
  Aside from `body`, the fields are assumed to be attributes of `page`.

- `lunr_languages`: A two-letter language code or a list of such codes,
  indicating which language(s) to use for stemming when building a Lunr index.
  The default language is `en`. For more on this,
  see the "Site search using Lunr" section below.

- `http`: This is is a dict for configuring the address used for `wmk serve`.
  It may contain either or both of two keys: `port` (default: 7007) and `ip`
  (default: 127.0.0.1). Can also be set directly via command line options.

- `mako_imports`: A list of Python statements to add to the top of each
  generated Mako template module file. Generally these are import statements.

- `theme`: This is the name of a subdirectory to the directory `$basedir/themes`
  (or a symlink placed there) in which to look for extra `static`, `assets`, `py`
  and `template` directories. Note that neither `content` nor `data` directories
  of a theme will be used by `wmk`. A theme-provided template may be rendered as
  stand-alone page, but only if no local template overrides it (i.e. has the
  same relative path). Mako's internal template lookup will similarly first look
  for referenced components in the normal `template` directory before looking in
  the theme directory.

- `extra_template_dirs`: A list of directories in which to look for Mako
  templates. These are placed after both `$basedir/templates` and theme-provided
  templates in the Mako search path. This makes it possible to build up a
  library of Mako components which can be easily used on multiple sites and
  across different themes.

[pymarkdown]: https://python-markdown.github.io/
[pypandoc]: https://github.com/NicklasTegner/pypandoc
[ext]: https://python-markdown.github.io/extensions/
[other]: https://github.com/Python-Markdown/markdown/wiki/Third-Party-Extensions


<!-- pandoc "A note on Pandoc" 80 -->

## A note on Pandoc

Pandoc's variant of Markdown is very featureful and sophisticated, but since its
use in `wmk` involves spawning an external process for each Markdown file being
converted, it is quite a bit slower than Python-Markdown. Therefore, it is
only recommended if you really do need it. Often, even if you do, it can be
turned on for individual pages or site sections rather than for the entire site.

If you decide to use Pandoc for a medium or large site, it is recommended to
turn the `use_cache` setting on in the configuration file. When doing this,
be aware that content that is sensitive to changes apart from the content file
will need to be marked as non-cacheable by adding `no_cache: true` to the
frontmatter. If you for instance call the `pagelist()` shortcode in the page,
you would as a rule want to mark the file in this way.

The `markdown_extensions` setting will of course not affect `pandoc`, but there
is one extension which is partially emulated in `wmk`'s Pandoc setup, namely
[toc](https://python-markdown.github.io/extensions/toc/).

If the `toc` frontmatter variable is true and the string `[TOC]` is
present on a separate line in a Markdown document which is to be processed by
pandoc, then it will be asked to generate a table of contents which will be
placed in the indicated location, just like the `toc` extension for
Python-Markdown does. The `toc_depth` setting (whose default value is 3) is
respected as well, although only in its integer form and not as a range (such as
`"2-4"`).


<!-- themes "Available themes" 90 -->

## Available themes

Currently there are three wmk themes available:

- [Lanyonesque][lanyonesque], a blog-oriented theme based on the Jekyll theme
  [Lanyon][lanyon]. [Demo][ldemo].

- [Historia][historia], a flexible single-page theme based on the [Story][story]
  template by [HTML5 UP][html5up]. [Demo][hdemo].

- [Picompany][pcomp], a general-purpose theme based on the [Company][company]
  template that accompanies the [PicoCSS][pico] documentation. [Demo][pdemo].

[lanyonesque]: https://github.com/bk/lanyonesque
[lanyon]: https://github.com/poole/lanyon
[ldemo]: https://lanyonesque.baldr.net/
[historia]: https://github.com/bk/historia
[story]: https://html5up.net/story
[html5up]: https://html5up.net/
[hdemo]: https://historia.baldr.net/
[pcomp]: https://github.com/bk/picompany
[company]: https://picocss.com/examples/company/
[pico]: https://picocss.com/
[pdemo]: https://picompany.baldr.net/

<!-- shortcodes "Shortcodes" 100 -->

## Shortcodes

A shortcode consists of an opening tag, `{{<`, followed by any number of
whitespace characters, followed by a string representing the "short version" of
the content, followed by any number of whitespace characters and the closing tag
`>}}`.

A typical use case is to easily embed content from external sites into your
Markdown. More advanced possibilities include formatting a table containing data
from a CSV file or generating a cropped and scaled thumbnail image.

Shortcodes are implemented as Mako components named `<shortcode>.mc` in the
`shortcodes` subdirectory of `templates` (or of some other directory in your
Mako search path, e.g. `themes/<my-theme>/templates/shortcodes`).

The shortcode itself looks like a function call. Note that positional
arguments can only be used if the component has an appropriate `<%page>`
block declaring the exepected arguments.

The shortcode component will have access to a context composed of (1) the
parameters directly specified in the shortcode call; (2) the information from
the metadata block of the markdown file in which it appears; (3) a counter
variable, `nth`, indicating number of invocations for that kind of shortcode in
that markdown document; (4) `LOOKUP`, the Mako `TemplateLookup` object; and (5)
the global template variables.

Shortcodes are applied **before** the Markdown document is converted to HTML, so
it is possible to replace a shortcode with Markdown content which will then be
processed normally.

A consequence of this is that shortcodes do **not** have direct access to (1)
the list of files to be processed, i.e. `MDCONTENT`, or (2) the rendered HTML
(including the parts supplied by the Mako template). A shortcode which needs
either of these must place a (potential) placeholder in the Markdown source as
well as a callback in `page.POSTPROCESS`. Each callback in this list will be
called just before the generated HTML is written to `htdocs/`, receiving the
full HTML as a first argument followed by the rest of the context for the page.
Examples of such shortcodes are `linkto` and `pagelist`, described below. (For
more on `page.POSTPROCESS` and `page.PREPROCESS`,
see the "Site and page variables" section below).

Here is an example of a shortcode in Markdown:

```markdown
### Yearly expenses

{{< csv_table('expenses_2021.csv') >}}
```

Here is an example `csv_table.mc` Mako component that might handle the above
shortcode call:

```mako
<%page args="csvfile, delimiter=',', caption=None"/>
<%! import os, csv %>
<%
info = []
with open(os.path.join(context.get('DATADIR'), csvfile.strip('/'))) as f:
    info = list(csv.DictReader(f, delimiter=delimiter))
if not info:
    return ''
keys = info[0].keys()
%>
<table class="csv-table">
  % if caption:
    <caption>${ caption }</caption>
  % endif
  <thead>
    <tr>
      % for k in keys:
        <th>${ k }</th>
      % endfor
    </tr>
  </thead>
  <tbody>
    % for row in info:
      <tr>
        % for k in keys:
          <td>${ row[k] }</td>
        % endfor
      </tr>
    % endfor
  </tbody>
</table>
```

Shortcodes can take up more than one line if desired, for instance:

```markdown
{{< figure(
      src="/img/2021/11/crocodile-or-alligator.jpg",
      caption="""
Although they appear similar, **crocodiles** and **alligators** differ in easy-to-spot ways:

- crocodiles have narrower and longer heads;
- their snouts are more V-shaped;
- also, crocodiles have a protruding tooth, visible when their mouth is closed.
""") >}}
```

In this example, the caption contains Markdown which would be converted to HTML
by the shortcode component.

Note that shortcodes are not escaped inside code blocks, so if you need to show
examples of shortcode usage in your content they must be escaped in some way in
such contexts.  One relatively painless way is to put a non-breaking space
character after the opening tag `{{<` instead of a space.

### Default shortcodes

The following default shortcodes are provided by the `wmk` installation:

- `figure`: An image wrapped in a `<figure>` tag. Accepts the following
  arguments: `src` (the image path or URL), `img_link`, `link_target`,
  `caption`, `figtitle`, `alt`, `credit` (image attribution), `credit_link`,
  `width`, `height`, `resize`.  Except for `src`, all arguments are optional.
  The caption and credit will be treated as markdown. If `resize` is True and
  width and height have been provided, then a resized version of the image is
  used instead of the original via the `resize_image` shortcode (the details can
  be controlled by specifying a dict representing `resize_image` arguments
  rather than a boolean; see below).

- `gist`: A Github gist. Two arguments, both required: `username` and `gist_id`.

- `include`: Insert the contents of the named file at this point.
  One required argument: `filename`. Optional argument: `fallback` (which
  defaults to the empty string), indicating what to show if the file is not
  found. The file must be inside the content directory (`CONTENTDIR`), otherwise
  it will not be read. The path is interpreted as relative to the directory in
  which the Markdown file is placed. A path starting with `/` is taken to start
  at `CONTENTDIR`.  Nested includes are possible but the paths of subincludes
  are interpreted relative to the original directory (rather than the directory
  in which the included file has been placed). Note that `include()` is always
  handled before other shortcodes.

- `linkto`: Links to the first matching (markdown-based) page. The first
  parameter, `page`, specifies the page which is to be linked to. This is either
  (a) a simple string representing a slug, title, (partial) path/filename or
  (partial) URL; or (b) a `match_expr` in the form of a dict or list which will
  be passed to `page_match()` with a `limit` of 1. Optional arguments: `label`
  (the link text; the default is the title of the matching page); `ordering`,
  passed to `page_match()` if applicable; `fallback`, the text to be shown if
  no matching page is found: `(LINKTO: page not found)` by default; the
  boolean `unique`, which if set to True causes a fatal error to be raised if
  multiple pages are found to match; and `link_attr`, which is a string to
  insert into the `<a>` tag (by default `class="linkto"`). A query string or
  anchor ID fragment for the link can be added via `link_append`, e.g.
  `link_append='#section2'` or `link_append='?q=searchstring'`.

- `pagelist`: Runs a `page_match()` and lists the found pages. Required argument:
  `match_expr`. Optional arguments: `ordering`, `limit`, `template`. The default
  is a simple unordered list of links to the found pages, using the page titles
  as the link text. If nothing is found, a string specified in the `fallback`
  parameter (by default an empty string) replaces the shortcode call. The
  formatting of the list can be changed by pointing to a Mako template using the
  `template` argument, which will receive a single argument, `pagelist` (a
  `MDContentList` of found pages). The template will only be called if something
  is found.

- `resize_image`: Scales and crops images to a specified size. Required
  arguments: `path`, `width`, `height`. Optional arguments: `op` ('fit_width',
  'fit_height', 'fit', 'fill'; the last is the default), `format` ('jpg' or
  'png'; default is 'jpg'), `quality` (default 0.75 and applies only to jpegs).
  Returns a path under `/resized_images/` (possibly prefixed with the value of
  `site.leading_path`) pointing to the resized version of the image.  The
  filename is a SHA1 hash + an extension, so repeated requests for the same
  resize operation are only performed once.  The source `path` is taken to be
  relative to the `WEBROOT`, i.e. the project `htdocs` directory.

- `template`: Calls the Mako template named in the first argument. Any
  additional arguments are passed directly on to the template (which will also
  see the normal Mako context for the shortcode itself).

- `twitter`: A tweet. Takes a `tweet_id`, which may be a Twitter status URL or
  the last part (i.e. the actual ID) of the URL.

- `vimeo`: A Vimeo video. One required argument: `id`. Optional arguments:
  `css_class`, `autoplay`, `dnt` (do not track), `muted`, `title`.

- `youtube`: A YouTube video. One required argument: `id`. Optional arguments:
  `css_class`, `autoplay`, `title`.

- `var`: The value of a variable, e.g. `"page.title"` or `"site.description"`.
  One required argument: `varname`. Optional argument: `default` (which defaults
  to the empty string), indicating what to show if the variable is not available.

<!-- pagevars "Site and page variables" 110 -->

## Site and page variables

When a markdown file is rendered, the Mako template receives a number of
context variables as partly described above. A few of these variables, such as
`MDTEMPLATES` and `DATADIR` set directly by `wmk` (see above). Others are
user-configured either (1) in `wmk_config.yaml` (the contents of the `site`
object and potentially additional "global" varaibles in `template_context`); or
(2) the cascade of `index.yaml` files in the `content` directory and its
subdirectories along with the YAML frontmatter of the markdown file itself, the
result of which is placed in the `page` object. 

When gathering the content of the `page` variable, `wmk` will
start by looking for `index.yaml` files in each parent directory of the markdown
file in question, starting at the root of the `content` directory and moving
upwards, at each step extending and potentially overriding the data gathered at
previous stages. Only then will the YAML in the frontmatter of the file itself
be parsed and added to the `page` data.

At any point, a data source in this cascade may specify an extra YAML file using
the special `LOAD` variable. This file will then be loaded as well and
subsequently treated as if the data in it had been specified directly at the
start of the file containing the `LOAD` directive.

Which variables are defined and used by templates is very much up the user,
although a few of them have a predefined meaning to `wmk` itself. For making it
easier to switch between different themes it is however suggested to stick to
the following meaning of some of the variables:

The variables `site` and `page` are dicts with a thin convenience layer on top
which makes it possible to reference subkeys belonging to them in templates
using dot notation rather than subscripts. For instance, if `page` has a dict
variable named `foo`, then a template could contain a fragment such as
`${ page.foo.bar or 'splat' }` -- even if the `foo` dict does not contain a key
named `bar`. Without this syntactic sugar you would have to write something much
more defensive and long-winded such as  `${ page.foo.bar if page.foo and 'bar'
in page.foo else 'splat' }`.

### System variables

The following frontmatter variables affect the operation of `wmk` itself, rather
than being exclusively handled by Mako templates.

#### Templates

**Note** that a variable called something like `page.foo` below is referenced as
such in Mako templates but specified in YAML frontmatter simply as `foo:
somevalue`.

- `page.template` specifies the Mako template which will render the content.

- `page.layout` is used by several other static site generators. For
  compatibility with them, this variable is supported as a fallback synonym with
  `template`.  It has no effect unless `template` has not been specified
  explicitly anywhere in the cascade of frontmatter data sources.

For both `template` and `layout`, the `.mhtml` extension of the template may be
omitted. If the `template` value appears to have no extension, `.mhtml` is
assumed; but if the intended template file has a different extension, then it
of course cannot be omitted.

Likewise, a leading `base/` directory may be omitted when specifying `template`
or `layout`. For instance, a `layout` value of `post` would find the template
file `base/post.mhtml` unless a `post.mhtml` file exists in the template root
somewhere in the template search path.

If neither `template` nor `layout` has been specified and no `default_template`
setting is found in `wmk_config.yaml`, the default template name for markdown
files is `md_base.mhtml`.

#### Affects rendering

- `page.slug`: If the value of `slug` is nonempty and consists exclusively of
  lowercase alphanumeric characters, underscores and hyphens (i.e. matches the
  regular expression `^[a-z0-9_-]+$`), then this will be used instead of the
  basename of the markdown file to determine where to write the output.
  If a `slug` variable is missing, one will be automatically added by `wmk`
  based on the basename of the current markdown file. Templates should therefore
  be able to depend upon slugs always being present. Note that slugs are not
  guaranteed to be unique, although that is good practice.

- `page.pretty_path`: If this is true, the basename of the markdown filename (or the
  slug) will become a directory name and the HTML output will be written to
  `index.html` inside that directory. By default it is false for files named
  `index.md` and true for all other files. If the filename contains symbols that
  do not match the character class `[\w.,=-]`, then it will be "slugified" before
  final processing (although this only works for languages using the Latin
  alphabet).

- `page.do_not_render`: Tells `wmk` not to write the output of this template to
  a file in `htdocs`. All other processing will be done, so the gathered
  information can be used by templates for various purposes. (This is similar to
  the `headless` setting in Hugo).

- `page.draft`: If this is true, it prevents further processing of the markdown
  file unless `render_drafts` has been set to true in the config file.

- `page.no_cache`: If this is true, the Markdown rendering cache will not be
  used for this file. (See also the `use_cache` setting in the configuration
  file).

- `page.markdown_extensions`, `page.markdown_extension_configs`, `page.pandoc`,
  `page.pandoc_filters`, `page.pandoc_options`, `page.pandoc_input_format`,
  `page.pandoc_output_format`: See the description of these options in the
  section on the configuration file, above.

- `page.POSTPROCESS`: This contains a list of processing instructions which are
  called on the rendered HTML just before writing it to the output directory.
  Each instruction is either a function (placed into `POSTPROCESS` by a
  shortcode) or a string (possibly specified in the frontmatter). If the latter,
  it points to a function entry in the `autoload` dict imported from either the
  project's `py/wmk_autoload.py` file or the theme's `py/wmk_theme_autoload.py`
  file.  In either case, the function receives the html as the first argument
  while the rest of the arguments constitute the template context. It should
  return the processed html.

- `page.PREPROCESS`: This is analogous to `page.POSTPROCESS`, except that the
  instructions in the list are applied to the Markdown just before converting it
  to HTML. The function receives two arguments: the Markdown document text and
  the `page` object. It should return the altered Markdown.

Note that if two files in the same directory have the same slug, they may both
be rendered to the same output file; it is unpredictable which of them will go
last (and thus "win the race"). The same kind of conflict may arise between a
slug and a filename or even between two filenames containing non-ascii
characters. It is up to the content author to take care to avoid this; `wmk`
does nothing to prevent it.

### Standard variables and their recommended meaning

The following variables are not used directly by `wmk` but affect templates in
different ways. It is a list of recommendations rather than something which
must be followed at all costs.

#### Typical site variables

Site variables are the keys-value pairs under `site:` in `wmk_config.yaml`.

- `site.title`: Name or title of the site.

- `site.lang`: Language code, e.g. 'en' or 'en-us'.

- `site.tagline`: Subtitle or slogan.

- `site.description`: Site description.

- `site.author`: Main author/proprietor of the site. Depending on the site
  templates (or the theme), may be a string or a dict with keys such as "name",
  "email", etc.

- `site.base_url`: The protocol and hostname of the site (perhaps followed by a
  directory path if `site.leading_path` is not being used). Normally without a
  trailing slash.

- `site.leading_path`: If the web pages built by `wmk` are not at the root of
  the website but in a subdirectory, this is the appropriate prefix path.
  Normally without a trailing slash.

- `site.build_time`: This is automatically added to the site variable by `wmk`.
  It is a datetime object indicating when the rendering phase of the current
  run started.

Templates or themes may be configurable through various site variables, e.g.
`site.paginate` for number of items per page in listings or `site.mainfont` for
configuring the font family.

#### Classic meta tags

These variables mostly relate to the text content and affect the metadata
section of the `<head>` of the HTML page.

- `page.title`: The title of the page, typically placed in the `<title>` tag in the
  `<head>` and used as a heading on the page. Normally the title should not be
  repeated as a header in the body of the markdown file. Most markdown documents
  should have a title.

- `page.description`: Affects the `<meta name="description" ...>` tag in the `<head>`
  of the page. The variable `summary` (see later) may also be used as fallback
  here.

- `page.keywords`: Affects the `<meta name="keywords" ...>` tag in the `<head>`
  of the page. This may be either a list or a string (where items are separated
  with commas).

- `page.robots`: Instructions for Google and other search engines relating to
  this content (e.g. `noindex, nofollow`) should be placed in this variable.

- `page.author`: The name of the author (if there is only one). May lead to `<meta
  name="keywords" ...>` tag in the `<head>` as well as appear in the body of the
  rendered HTML file. Some themes may expect this to be a dict with keys such
  as `name`, `email`, `image`, etc.

- `page.authors`: If there are many authors they may be specified here as a list.
  It is up to the template how to handle it if both `author` and `authors` are
  specified, but one way is to add the `author` to the `authors` unless already
  present in the list.

- `page.summary`: This may affect the `<meta name="description" ...>` tag as a
  fallback if no `description` is provided, but its main purpose is for list
  pages with article teasers and similar content.

Note that this is by no means an exhaustive list of variables likely to affect
the `<head>` of the page. Notably, several other variables may affect meta tags
used for sharing on social media. The most common is probably `page.image`
(described below). In any case, the implementation itself is up to the theme or
template author.

#### Dates

Dates and datetimes should normally be in a format conformant with or similar to
ISO 8601, e.g. `2021-09-19` and `2021-09-19T09:19:21+00:00`. The `T` may be
replaced with a space and the time zone may be omitted (localtime is assumed).
If the datetime string contains hours it should also contain minutes, but
seconds may be omitted. If these rules are followed, the following variables
are converted to date or datetime objects (depending on the length of the
string) before they are passed on to templates.

- `page.date`: A generic date or datetime associated with the document.

- `page.pubdate`: The date/datetime when first published. Currently `wmk` does not
  skip files with `pubdate` in the future, but it may do so in a later version.

- `page.modified_date`: The last-modified date/datetime. Note that `wmk` will also
  add the variable `MTIME`, which is the modification time of the file
  containing the markdown source, so this information can be inferred from
  that if this variable is not explicitly specified.

- `page.created_date`: The date the document was first created.

- `page.expire_date`: The date from which the document should no longer be published.
  Similarly to `pubdate`, this currently has no direct effect on `wmk` but may
  do so in a later version.

See also the description of the `DATE` and `MTIME` context variables above.

#### Media content

- `page.image`: The main image associated with the document. Affects the `og:image`
  meta tag in HTML output and may be used for both teasers and content rendering.

- `page.images`: A list of images associated with the document. If `image` is not
  specified, the main image will be taken to be the first in the list.

- `page.audio`: A list of audio files/urls associated with this document.

- `page.videos`: A list of video files/urls associated with this document.

- `page.attachments`: A list of attachments (e.g. PDF files) associated with this
  document.

#### Taxonomy

- `page.section`: One of a quite small number of sections on the site, often
  corresponding to the leading subdirectory in `content`. E.g.  "blog", "docs",
  "products".

- `page.categories`: A list of broad categories the page belongs to. E.g. "Art",
  "Science", "Food". The first-named category may be regarded as the primary
  one.

- `page.tags`: A list of tags relevant to the content of the page. E.g. "quantum
  physics", "knitting", "Italian food".

- `page.weight`: A measure of importance attached to a page and used as an ordering
  key for a list of pages. This should be a positive integer. The list is
  normally ascending, i.e. with the lower numbers at the top. (Pages may of
  course be ordered by other criteria, e.g. by `pubdate`).

<!-- template_filters "Template filters" 120 -->

## Template filters

In addition to the [built-in template
filters](https://docs.makotemplates.org/en/latest/filtering.html) provided by
Mako, the following filters are by default made available in templates:

- `date`: date formatting using strftime. By default, the format '%c' is used.
  A different format is specified using the `fmt` parameter, e.g.:
  `${ page.pubdate | date(fmt=site.date_format) }`.

- `date_to_iso`: Format a datetime as ISO 8601 (or similarly, depending on
  parameters). The parameters are `sep` (the separator between the date part and
  the time part; by default 'T', but a space is sensible as well); `upto` (by
  default 'sec', but 'day',  'hour' and 'frac' are also acceptable values); and
  `with_tz` (by default False).

- `date_to_rfc822`: Format a datatime as RFC 822 (a common datetime format in
  email headers and some types of XML documents).

- `date_short`: E.g. "7 Nov 2022".

- `date_short_us`: E.g. "Nov 7th, 2022".

- `date_long`: E.g. "7 November 2022".

- `date_long_us`: E.g. "November 7th, 2022".

- `slugify`: Turns a string into a slug. Only works for strings in the Latin
  alphabet.

- `markdownify`: Convert Markdown to HTML. It is possible to specify custom
  extensions using the `extensions` argument.

- `truncate`: Convert markdown/html to plaintext and return the first `length`
  characters (default: 200), with an `ellipsis` (default: "…") appended if any
  shortening has taken place.

- `truncate_words`: Convert markdown/html to plaintext and return the first
  `length` words (default: 25), with an `ellipsis` (default "…") appended if any
  shortening has taken place.

- `p_unwrap`: Remove a wrapping `<p>` tag if and only if there is only one
  paragraph of text. Suitable for short pieces of text to which a markdownify
  filter has previously been applied. Example: `<h1>${ page.title |
  markdownify,p_unwrap }</h1>`.

- `strip_html`: Remove any markdown/html markup from the text. Paragraphs will
  not be preserved.

- `cleanurl`: Remove trailing 'index.html' from URLs.

If you wish to provide additional filters without having to explicitly define or
import them in templates, the best way of doing this his to add them via the
`mako_imports` setting in `wmk_config.yaml` (see above).

Please note that in order to avoid conflicts with the above filters you should
not place a file named `wmk_mako_filters.py` in your `py/` directories.

<!-- mdcontentlist "Working with lists of pages" 130 -->

## Working with lists of pages

Templates which render a list of content files (e.g. a list of blog posts or
pages belonging to a category) will need to filter or sort `MDCONTENT`
accordingly. In order to make this easier, `MDCONTENT` is wrapped in a list-like
object called `MDContentList`, which has the following methods:

### General searching/filtering

Each of the following methods returns a new `MDContentList` containing those
entries for which the predicate (`pred`) is True.

- `match_entry(self, pred)`: The `pred` (i.e. predicate) is a callable which
  receives the full information on each entry in the `MDContentList` and returns
  True or False. 

- `match_ctx(self, pred)`: The `pred` receives the context for each entry and
  returns a boolean.

- `match_page(self, pred)`: The `pred` receives the `page` object for each entry
  and returns a boolean.

- `match_doc(self, pred)`: The `pred` receives the markdown body for each entry
  and returns a boolean.

- `url_match(self, url_pred)`: The `pred` receives the `url` (relative to
  `htdocs`) for each entry and returns a boolean.

- `path_match(self, src_pred)`: The `pred` receives the path to the Markdown
  source for each entry and returns a boolean.

### Specialized searching/filtering

All of these return a new `MDContentList` object.

- `posts(self, ordered=True)`: Returns a new `MDContentList` with those entries
  which are blog posts. In practice this means those with markdown sources in
  the `posts/` or `blog/` subdirectories or those which have a `page.type` of
  "post", "blog", "blog-entry" or "blog_entry". Normally ordered by date (newest
  first), but this can be turned off by setting `ordered` to False.

- `in_date_range(self, start, end, date_key='DATE')`: Posts/pages with a date
  between `start` and `end`. The key for the date field can be specifed using
  `date_key`.  Unless the value for `date_key` is either `DATE` or `MTIME`, then
  the key is looked for in the `page` variables for the entry.

- `has_taxonomy(self, haystack_keys, needles)`: A general search for entries
  belonging to a taxonomy group, such as category, tag, section or type. They
  `haystack_keys` are the `page` variables to examine while `needles` is a list
  of the values to look for in the values of those variables. A string value for
  `needles` is treated as a one-item list. The search is case-insensitive.

- `in_category(self, catlist)`: A shortcut method for
  `self.has_taxonomy(['category', 'categories'], catlist)`

- `has_tag(self, taglist)`: A shortcut method for `self.has_taxonomy(['tag',
  'tags'], taglist)`.

- `in_section(self, sectionlist)`: A shortcut method for
  `self.has_taxonomy(['section', 'sections'], sectionlist)`.

- `page_match(self, match_expr, ordering=None, limit=None)`: This is actually
  quite a general matching method but does not require the caller to pass a
  predicate callable to it, which means that it can be employed in more varied
  contexts than the general methods described in the last section. A
  `match_expr` contains the filtering specification. It will be described
  further below. The `ordering` parameter, if specified, should be either
  `title`, `slug`, `url` or `date`, with an optional `-` in front to indicate
  reverse ordering. The `date` option for `ordering` may be followed by the
  preferred frontmatter date field after a colon, e.g.
  `ordering='-date:modified_date'` for a list with the most recently changed
  files at the top. The `limit`, if specified, obviously indicates the maximum
  number of pages to return.

A `match_expr` for `page_match()` is either a dict or a list of dicts.  If it is
a dict, each page in the result set must match each of the attributes specified
in it. If it is a list of dicts, each page in the result set must match at least
one of the dicts (i.e., the returned result set contains the union of all
matches from all dicts in the list). When a string or regular expression match
is being performed in this process, it will be case-insensitive. The supported
attributes (i.e. dict keys) are as follows:

- `title`: A regular expression which will be applied to the page title.
- `slug`: A regular expression which will be applied to the slug.
- `url`: A regular expression which will be applied to the target URL.
- `path`: A regular expression which will be applied to the path to the markdown
  source file (i.e. the `source_file_short` field).
- `doc`: A regular expression which will be applied to the body of the markdown
  source document.
- `date_range`: A list containing two ISO-formatted dates and optionally a date
  key (`DATE` by default) - see the description of `in_date_range()` above.
- `has_attrs`: A list of frontmatter variable names. Matching pages must have a
  non-empty value for each of them.
- `attrs`: A dict where each key is the name of a frontmatter variable and the
  value is the value of that attribute. If the value is a string, it will be
  matched case-insensitively. All key-value pairs must match.
- `has_tag`, `in_section`, `in_category`: The values are lists of tags, sections
  or categories, respectively, at least one of which must match
  (case-insensitively). See the methods with these names above.
- `is_post`: If set to True, will match if the page is a blog post; if set to
  False will match if the page is not a blog post.
- `exclude_url`: The page with this URL should be omitted from the results
  (normally the calling page).

### Sorting

All of these return a new `MDContentList` object with the entries in the
specified order.

- `sorted_by(self, key, reverse=False, default_val=-1)`: A general sorting
  method. The `key` is the `page` variable to sort on, `default_val` is the
  value to assume if there is no such variable present in the entry, while
  `reverse` indicates whether the sort is to be descending (True) or ascending
  (False, the default).

- `sorted_by_date(self, newest_first=True, date_key='DATE')`: Sorting by date,
  newest first by default. The date key to sort on can be specified if desired.

- `sorted_by_title(self, reverse=False)`: Sorting by `page.title`, ascending
  by default.

### Pagination

- `paginate(self, pagesize=5, context=None)`: Divides the `MDContentList` into
  chunks of size `pagesize` and returns a tuple consisting of the chunks and a
  list of `page_urls` (one for each page, in order). If an appropriate template
  context is provided, pages 2 and up will be written to the webroot output
  directory to destination files whose names are based upon the URL for the
  first page (and the page number, of course). Without the context, the
  `page_urls` will be None. It is the responsibility of the calling template to
  check the `_page` variable for the current page to be rendered (this defaults
  to 1). Each iteration will get all chunks and must use this variable to limit
  itself appropriately.

Typical usage of `paginate()`:

```mako
<%
  posts = MDCONTENT.posts()
  chunks, page_urls = posts.paginate(5, context)
  curpage = context.get('_page', 1)
%>

% for post in chunks[curpage-1]:
  ${ show_post(post) }
% endfor

% if len(chunks) > 1:
  ${ prevnext(len(chunks), curpage, page_urls) }
% endif
```

### Render to an arbitrary file

- `def write_to(self, dest, context, extra_kwargs=None, template=None)`:
  Calls a template with the `MDContentList` in `self` as the value of `CHUNK`
  and write the result to the file named in `dest`. The file is of course
  relative to the webroot.  Any directories are created if necessary. The
  `template` is by default the calling template while `extra_kwargs` may be
  added if desired.

Typical usage of `write_to()`:

```mako
<%
  if not CHUNK:
     for tag in tags:
         tagged = MDCONTENT.has_tag([tag])
         if not tagged:
             continue  # avoid potential infinite loop!
         outpath = '/tags/' + slugify(tag) + '/index.html'
         tagged.write_to(outpath, context, {'TAG': tag})
%>

% if CHUNK:
  ${ list_tagged_pages(TAG, CHUNK) }
% else:
  ${ list_tags() }
% endif
```

<!-- lunr "Site search using Lunr" 140 -->

## Site search using Lunr

With `lunr_index` (and optionally `lunr_index_fields`) in `wmk_config.yaml`, wmk
will build a search index for [Lunr.js](https://lunrjs.com/) and place it in
`idx.json` in the webroot. In order to minimize its size, no metadata about
each record is saved to the index. Instead, a simple list of pages (with title
and summary) is placed in `idx.summaries.json`. The summary is taken either from
one of the frontmatter fields `summary`, `intro` or `description` (in order of
preference) or, failing that, from the start of the page body.

If `lunr_languages` is present in `wmk_config.yaml`, stemming rules for those
languages will be applied when building the index. The value may be a two-letter
lowercase country code (ISO-639-1) or a list of such codes. The currently
accepted languages are `de`, `da`, `en`, `fi`, `fr`, `hu`, `it`, `nl`, `no`,
`pt`, `ro`, and `ru` (this is the intersection of the languages supported by
`lunr.js` and NLTK, respecively). The default language is `en`. Attempting to
specify a non-supported language will raise an exception.

The index is built via the [`lunr.py`](https://lunr.readthedocs.io/en/latest/)
module and the stemming support is provided by the Python [Natural Language
Toolkit](https://www.nltk.org/).

For information about the supported syntax of the search expression, see the
[Lunr documentation](https://lunrjs.com/guides/searching.html).

### Limitations

- Building the index does not mean that the search functionality is complete. It
  remains to point to `lunr.js` in the templates and write some javascript to
  interface with it and display the results.  However, since every website is
  different, this cannot be provided by wmk directly. It is up to the template
  (or theme) author to actually load the index and present a search interface to
  the user.

- Similarly, if a "fancy" preview of results is required which cannot be fulfilled
  using the information in `idx.summaries.json`, this must currently be solved
  independently by the template/theme author.

- Note that only the raw Markdown content is indexed, not the HTML after the
  Markdown has been processed. The output of Mako templates (including shortcodes)
  is not indexed either.
