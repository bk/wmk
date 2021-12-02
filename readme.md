# wmk

This is a simple static site generator written in Python with the following
main features:

- Markdown content with YAML metadata.
- Additional data may be loaded from separate YAML files.
- The content is rendered using [Mako][mako] templates.
- Stand-alone templates are also rendered if present.
- Configurable shortcodes (though none built-in at present).
- Sass/SCSS support.
- Support for themes.

[mako]: https://www.makotemplates.org/

## Getting ready

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
- For `wmk watch` functionality, you need to be using Linux and have
  `inotifywait` installed.

## Usage

The `wmk` command structure is `wmk <action> <base_directory>`. The base
directory is of course the directory containing the source files in
subdirectories such as `templates`, `content`, etc.  See below for details on
file organization.

- `wmk info $basedir`: Shows the real path to the location of `wmk.py` and of
  the content base directory. E.g. `wmk info .`. Synonyms for `info` are `env`
  and `debug`.

- `wmk run $basedir [-f|--force]`: Compiles/copies files into `$basedir/htdocs`.
  If `-f` or `--force` is specified as the third argument, no timestamp checking
  is done, resulting in all files being re-processed. Synonyms for `run` are
  `build`, `b` and `r`.

- `wmk watch $basedir [-f|--force]`: Watches for changes in the source
  directories inside `$basedir` and recompiles if changes are detected.  If `-f`
  or `--force` is specified as the third argument, no timestamp checking is done
  whenever a potential change triggers a rerun of `wmk run`, thus ensuring that
  all files will be re-processed. A synonym for `watch` is `w`.

- `wmk serve $basedir`: Serves the files in `$basedir/htdocs` on
  `http://localhost:7007/` (the IP and port are configurable via
  `wmk_config.yaml` – see below). Synonyms for `serve` are `srv` and `s`.

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
  stand-alone templates, see below.

- `content`: Markdown content with YAML metadata. This will be rendered into
  html using the `template` specified in the metadata or `md_base.mhtml` by
  default. The target filename will be `index.html` in a directory corresponding
  to the basename of the markdown file, unless `pretty_path` in the metadata is
  `false` or the name of the Markdown file itself is `index.md` (in which case
  only the extension is replaced). The converted content will be passed to the
  Mako template as a string in the context variable `CONTENT`, along with other
  metadata. A YAML datasource can be specified in the metadata block as `LOAD`;
  the data in this file will be added to the context. For further details on the
  context variables, see below.

- `data`: YAML files for additional metadata.

- `assets`: Assets for an asset pipeline. Currently this only handles SCSS/Sass
  files in the subdirectory `scss`. They will be compiled to CSS which is placed
  in the target directory `htdocs/css`.

- `static`: Static files. Everything in here will be rsynced directoy over to
  `htdocs`.

## Notes

* The order of operations is as follows: (1) Copy files from `static/`; (2) run
  asset pipeline; (3) render Mako templates from `templates`; (4) render
  Markdown content from `content`.

  Note that later steps may overwrite files placed by earlier steps.

* For the `run` and `watch` actions, `wmk.py` uses timestamps to prevent
  unnecessary re-rendering of templates, markdown files and scss sources. The
  check is rather primitive so it may be necessary to touch the main source file
  or remove files from `htdocs` in order to trigger a refresh. To force a
  rebuild of all files, one can also use the `--force` (or `-f`) switch as
  an extra argument.

* If files are removed from source directories the corresponding files in
  `htdocs` will not disappear automatically. You have to clear them out
  manually.

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
- `MDCONTENT`: A list representing all the markdown files which will potentially
  be rendered by a template. Each item in the list contains the keys
  `source_file`, `source_file_short` (truncated and full paths to the source),
  `target` (html file to be written), `template` (filename of the template which
  will be used for rendering), `data` (most of the context variables seen by
  this content), `doc` (the raw markdown source), and `url` (the `SELF_URL`
  value for this content – see below). If the configuration setting `pre_render`
  is True, then `rendered` (the HTML produced by converting the markdown) is
  present as well. Note that `MDCONTENT` is not available inside shortcodes.
- Whatever is defined under `template_context` in the `wmk_config.yaml` file
  (see below).
- `SELF_URL`: The relative path to the HTML file which the output of the
  template will be written to.

When templates are rendering Markdown content, they additionally get the
following context variables:

- `CONTENT`: The rendered HTML produced from the markdown source.
- `RAW_CONTENT`: The original markdown source.
- `MTIME`: A datetime object representing the modification time for the markdown
  file.
- `RENDERER`: A callable which enables a template to render markdown in `wmk`'s
  own environment. This is mainly so that it is possible to support shortcodes
  which depend on other markdown content which itself may contain shortcodes.
  The callable receives a dict containing the keys `doc` (the markdown) and
  `data` (the context variables) and returns rendered HTML.
- Whatever is defined in the YAML meta section at the top of the markdown file,
  in the `template_context` section of `wmk_config.yaml`, as well as in
  `index.yaml` files in the markdown file directory and its parent directories
  inside `content`.

For further details on context variables set in the markdown frontmatter and in
`index.yaml` files, see below under "Frontmatter variables".

## Config file

A config file, `$basedir/wmk_config.yaml`, can be used to configure some aspects
of how `wmk` operates. Currently there is support for the following settings:

- `template_context`: Default values for the context passed to Mako templates.
  This should be a dict. The values may be overridden by markdown metadata or
  linked YAML files.

- `render_drafts`: Normally, markdown files with `draft` set to a true value in
  the metadata section will be skipped during rendering. This can be turned off
  (so that the `draft` status flag is ignored) by setting `render_drafts` to True
  in the config file.

- `markdown_extensions`: A list of [extensions][ext] to enable for markdown
  processing by Python-Markdown. The default is `['extra', 'sane_lists']`.
  If you specify [third-party extensions][other] here, you have to install them
  into the Python virtual environment first.

- `sass_output_style`: The output style for Sass/SCSS rendering. This should be
  one of `compact`, `compressed`, `expanded` or `nested`. The default is
  `expanded`.

- `http`: This is is a dict for configuring the address used for `wmk serve`.
  It may contain either or both of two keys: `port` (default: 7007) and `ip`
  (default: 127.0.0.1).

- `theme`: This is the name of a subdirectory to the directory `$basedir/themes`
  (or a symlink placed there) in which to look for extra `static`, `assets` and
  `template` directories. Note that neither `content` nor `data` directories
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

[ext]: https://python-markdown.github.io/extensions/
[other]: https://github.com/Python-Markdown/markdown/wiki/Third-Party-Extensions

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
the metadata block of the markdown file in which it appears; and (3) the global
template variables.

Shortcodes are applied **before** the Markdown document is converted to HTML, so
it is possible to replace a shortcode with Markdown content which will then be
processed normally.

Here is an example of a shortcode in Markdown:

```markdown
### Yearly expenses

{{< csv_table('expenses_2021.csv') >}}
```

Here is an example `csv_table.mc` Mako component that might handle the above
shortcode call:

```mako
<%page args="csvfile, delimiter=',', caption=None, **kwargs"/>
<%! import os, csv %>
<%
info = []
with open(os.path.join(kwargs['DATADIR'], csvfile)) as f:
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
{{< figure(
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

### Default shortcodes

The following default shortcodes are provided by `wmk`:

- `figure`: An image wrapped in a `<figure>` tag. Accepts the following
  arguments: `src` (the image path or URL), `link`, `caption`, `title`, `alt`,
  `credit` (image attribution), `credit_link`, `width`, `height`, `resize`.
  Except for `src`, all arguments are optional. The caption and credit will be
  treated as markdown. If `resize` is True and width and height have been
  provided, then a resized version of the image is used instead of the original
  via the `resize_image` shortcode (the details can be controlled by specifying
  a dict representing `resize_image` arguments rather than a boolean; see
  below).

- `gist`: A Github gist. Two arguments, both required: `username` and `gist_id`.

- `resize_image`: Required arguments: `path`, `width`, `height`. Optional
  arguments: `op` ('fit_width', 'fit_height', 'fit', 'fill'; the last is the
  default), `format` ('jpg' or 'png'; default is 'jpg'), `quality` (default
  0.75). Returns a path under `/resized_images/` (possibly prefixed with the
  value of `site_leading_path`) pointing to the resized version of the image.
  The filename is a SHA1 hash + an extension, so repeated requests for the same
  resize operation are only performed once.  The source `path` is taken to be
  relative to the `WEBROOT`, i.e. the project `htdocs` directory.

- `twitter`: A tweet. Takes a `tweet_id`, which may be a Twitter status URL or
  the last part (i.e. the actual ID) of the URL.

- `vimeo`: A Vimeo video. One required argument: `id`. Optional arguments:
  `css_class`, `autoplay`, `dnt` (do not track), `muted`, `title`.

- `youtube`: A YouTube video. One required argument: `id`. Optional arguments:
  `css_class`, `autoplay`, `title`.


## Frontmatter variables

When a markdown file is rendered, the Mako template receives a number of
variables as partly described above. A few of these variables, such as
`MDTEMPLATES` and `DATADIR` are set directly by `wmk` (see above). Others are
user-configured and set in one of the following places, with the last-mentioned
sources having the highest priority for any given variable name: (1)
`wmk_config.yaml`, under the key `template_context`; (2) the cascade of
`index.yaml` files in the `content` directory and its subdirectories; (3) the
YAML frontmatter of the markdown file itself. Let us call all of these
"frontmatter variables" for short, even if they are gathered from this cascade
of increasingly specific sources.

Before loading the frontmatter of the markdown file itself, `wmk` will thus
start by looking in `wmk_config.yamk` for whatever is defined in
`template_context`. Then it will loook for `index.yaml` files in each parent
directory of the markdown file in question, starting at the root of the
`content` directory and moving upwards, at each step extending and potentially
overriding the data gathered at previous stages. Only then will the YAML in the
frontmatter of the file itself be parsed and added to the data.

At any point, a data source in this cascade may specify an extra YAML file using
the special `LOAD` variable. This file will then be loaded as well and
subsequently treated as if the data in it had been specified directly in the
file with the `LOAD` directive.

Which variables are defined and used by templates is very much up the user,
although a few of them have a predefined meaning to `wmk` itself. For making it
easier to switch between diffent themes it is however suggested to stick to the
following meaning of some of the variables:

### System variables

The following frontmatter variables affect the operation of `wmk` itself, rather
than being exclusively handled by templates.

#### Templates

- `template` specifies the Mako template which will render the content.

- `layout` is used by several other static site generators. For compatibility
  with them, this variable is supported as fallback synonym with `template`.
  It has no effect unless `template` has not been specified explicitly anywhere
  in the cascade of frontmatter data sources.

For both `template` and `layout`, the `.mhtml` extension of the template may be
omitted. If the `template` value appears to have no extension, `.mhtml` is
assumed; but if the intended template file has a different extension, then it
of course cannot be omitted.

If neither `template` nor `layout` has been specified and no `default_template`
setting is found in `wmk_config.yaml`, the default template name for markdown
files is `md_base.mhtml`.

#### Affects rendering

- `slug`: If the value of `slug` is nonempty and consists exclusively of
  lowercase alphanumeric characters, underscores and hyphens (i.e. matches the
  regular expression `^[a-z0-9_-]+$`), then this will be used instead of the
  basename of the markdown file to determine where to write the output.
  If a `slug` variable is missing, one will be automatically added by `wmk`
  based on the basename of the current markdown file. Templates should therefore
  be able to depend upon slugs always being present. Note that slugs are not
  guaranteed to be unique, although that is good practice.

- `pretty_path`: If this is true, the basename of the markdown filename (or the
  slug) will become a directory name and the HTML output will be written to
  `index.html` inside that directory. By default it is false for files named
  `index.md` and true for all other files. If the filename contains symbols that
  do not match the character class `[\w.,=-]`, then it will be "slugified" before
  final processing (although this only works for languages using the Latin
  alphabet).

- `do_not_render`: Tells `wmk` not to write the output of this template to a
  file in `htdocs`. All other processing will be done, so the gathered information
  can be used by templates for various purposes. (This is similar to the
  `headless` setting in Hugo).

- `draft`: If this is true, it prevents further processing of the markdown file
  unless `render_drafts` has been set to true in the config file.

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

#### Classic meta tags

These variables mostly relate to the text content and affect the metadata
section of the `<head>` of the HTML page.

- `title`: The title of the page, typically placed in the `<title>` tag in the
  `<head>` and used as a heading on the page. Normally the title should not be
  repeated as a header in the body of the markdown file.

- `description`: Affects the `<meta name="description" ...>` tag in the `<head>`
  of the page. The variable `summary` (see later) may also be used as fallback
  here.

- `keywords`: Affects the `<meta name="keywords" ...>` tag in the `<head>`
  of the page. This may be either a list or a string (where items are separated
  with commas).

- `robots`: Instructions for Google and other search engines (e.g. `noindex,
  nofollow`) should be placed in this variable.

- `author`: The name of the author (if there is only one). May lead to `<meta
  name="keywords" ...>` tag in the `<head>` as well as appear in the body of the
  rendered HTML file.

- `authors`: If there are many authors they may be specified here as a list.
  It is up to the template how to handle it if both `author` and `authors` are
  specified, but one way is to add the `author` to the `authors` unless already
  present in the list.

- `summary`: This may affect the `<meta name="description" ...>` tag as a
  fallback if no `description` is provided, but its main purpose is for list
  pages with article teasers and similar content.

Note that this is by no means an exhaustive list of variables likely to affect
the `<head>` of the page. Notably, several other variables may affect meta tags
used for sharing on social media. The most common is probably `image` (described
below). In any case, the implementation itself is up to the theme or template
author.

#### Dates

Dates and datetimes should normally be in a format conformant with or similar to
ISO 8601, e.g. `2021-09-19` and `2021-09-19T09:19:21+00:00`. The `T` may be
replaced with a space and the time zone may be omitted (localtime is assumed).
If the datetime string contains hours it should also contain minutes, but
seconds may be omitted. If these rules are followed, the following variables
are converted to date or datetime objects (depending on the length of the
string) before they are passed on to templates.

- `date`: A generic date or datetime associated with the document.

- `pubdate`: The date/datetime when first published. Currently `wmk` does not
  skip files with `pubdate` in the future, but it may do so in a later version.

- `modified_date`: The last-modified date/datetime. Note that `wmk` will also
  add the variable `MTIME`, which is the modification time of the file
  containing the markdown source, so this information can be inferred from
  that if this variable is not explicitly specified.

- `created_date`: The date the document was first created.

- `expire_date`: The date from which the document should no longer be published.
  Similarly to `pubdate`, this currently has no effect on `wmk` but may do so in
  a later version.

#### Media content

- `image`: The main image associated with the document. Affects the `og:image`
  meta tag in HTML output and may be used for both teasers and content rendering.

- `images`: A list of images associated with the document. If `image` is not
  specified, the main image will be taken to be the first in the list.

- `audio`: A list of audio files/urls associated with this document.

- `videos`: A list of video files/urls associated with this document.

- `attachments`: A list of attachments (e.g. PDF files) associated with this
  document.

#### Taxonomy

- `section`: One of a quite small number of sections on the site, often
  corresponding to the leading subdirectory in `content`. E.g.  "blog", "docs",
  "products".

- `categories`: A list of broad categories the page belongs to. E.g. "Art",
  "Science", "Food". The first-named category may be regarded as the primary
  one.

- `tags`: A list of tags relevant to the content of the page. E.g. "quantum
  physics", "knitting", "Italian food".

- `weight`: A measure of importance attached to a page and used as an ordering
  key for a list of pages. This should be a positive integer. The list is
  normally ascending, i.e. with the lower numbers at the top. (Pages may of
  course be ordered by other criteria, e.g. by `pubdate`).

You should avoid having subdirectories named `categories` (or `category`) and
`tags` (or `tag`) in your `content` directory since it is likely that list
templates will be writing HTML content to the corresponding directories in
`htdocs`.
