# wmk

This is a simple static site generator written in Python with the following
features:

- Markdown content with YAML metadata.
- Additional data may be loaded from separate YAML files.
- The content is rendered using [Mako][mako] templates.
- Stand-alone templates are also rendered if present.
- Sass/SCSS support.
- Configurable shortcodes.

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
  rendered directly into `htdocs` as `.html` files, unless their filename starts
  with a dot or underscore or contains the string `base`, or if they are inside
  a subdirectory names `base`. For details on context variables received by such
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

## Context variables

The Mako templates, whether they are stand-alone or being used to render
Markdown content, receive the following context variables:

- `DATADIR`: The full path to the `data` directory.
- `WEBROOT`: The full path to the `htdocs` directory.
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
  present as well.
- Whatever is defined under `template_context` in the `wmk_config.yaml` file
  (see below).
- `SELF_URL`: The relative path to the HTML file which the output of the
  template will be written to.

When templates are rendering Markdown content, they additionally get the
following context variables:

- `CONTENT`: The rendered HTML produced from the markdown source.
- `RAW_CONTENT`: The original markdown source.
- Whatever is defined in the YAML meta section at the top of the markdown file.

## Notes

* The order of operations is as follows:

  1. Copy files from `static/`.
  2. Run asset pipeline.
  3. Render Mako templates from `templates`.
  4. Render Markdown content from `content`.

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

## Config file

A config file, `$basedir/wmk_config.yaml`, can be used to configure some aspects
of how `wmk` operates. Currently there is support for the following settings:

- `template_context`: Default values for the context passed to Mako templates.
  This should be a dict. The values may be overridden by markdown metadata or
  linked YAML files.

- `shortcodes` and `mako_shortcodes`: A way to mix complicated or dynamic
  content into Markdown with minimal effort. See further defails below.

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

- `pre_render`: If this is True, then the markdown source of each content file
  will be converted to HTML regardless of whether an output file will be written
  to `htdocs` or not (i.e. even if the timestamp of the output file is newer
  than the source and the `--force` has not been specified). This is mainly
  useful for list pages in `templates`, e.g. a blog frontpage with a list of
  blog entries.

[ext]: https://python-markdown.github.io/extensions/
[other]: https://github.com/Python-Markdown/markdown/wiki/Third-Party-Extensions

## Shortcodes

A shortcode consists of an opening tag, `{{<`, followed by any number of spaces,
followed by a string representing the "short version" of the content, followed
by any number of spaces and the closing tag `>}}`. It should stay on one line.

A typical use case is to easily embed content from external sites into your
Markdown. More advanced possibilities include formatting a table containing data
from a CSV file or generating a cropped and scaled thumbnail image.

There are two types of shortcodes: (1) regex-based shortcodes, defined directly
in `wmk_config.yaml`; and (2) shortcodes defined in a specified Mako template.

### Regex-based shortcodes

Here is an example of a simple regex-based shortcode for easily embedding
YouTube videos:

```markdown
{{< youtube p118YbxFtGg >}}
```

The value of the `shortcodes` section of the config file should be a dict where
the key is an identifier for the type of shortcode and the value should be a
dict with two keys, `pattern` and `content`. The pattern is a regular expression
and the content is substituted for the shortcode string. Here is a working example:

```yaml
shortcodes:
  youtube:
    pattern: youtube (\S+)
    content: >-
      <div class="video-container"><iframe
      width="560" height="315"
      src="https://www.youtube.com/embed/\g<1>"
      title="YouTube video player" frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen></iframe></div>
```

### Mako-based shortcodes

Mako-based shortcodes are implemented as `<%def>` blocks in a Mako component
inside the `templates` directory. The name of the component is specified in the
`wmk_config.yaml` file like this:

```yaml
mako_shortcodes: utils/shortcodes.mc
```

The shortcode itself looks like a function call along with an optional
single-word directive after the closing parenthesis. Currently only one
such directive is supported: `with_context` (or `ctx` for short). Without this
directive, the template def only receives the arguments that are directly
specified in the shortcode. With the directive, however, the context (i.e.
global template variables along with whatever is defined in the metadata block)
associated with the Markdown file containing the shortcode call is added to the
function keyword arguments when the template def is rendered. Here is an example
of a Mako-based shortcode call:

```markdown
{{< csv_table('expenses_2021.csv') with_context >}}
```

Here is an example `shortcodes.mc` Mako component implementing a `csv_table()`
that might handle the above shortcode call:

```mako
<%! import os, csv %>

<%def name="csv_table(cvsfile, delimiter=',', caption=None, **kwargs)">
<%
info = []
with open(os.path.join(kwargs['DATADIR'], cvsfile)) as f:
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
</%def>
```

Note that because we need to use a context variable (`DATADIR`), the shortcode
call includes the `with_context` directive, and for the same reason the Mako def
appends `**kwargs` to its list of arguments.

### Notes

Shortcodes are applied **before** the Markdown document is converted to HTML, so
it is possible to replace a shortcode with Markdown content which will then be
processed normally.

Mako-based shortcodes are applied before regex-based shortcodes.

Currently no default shortcodes are provided. In order to use them, they must be
configured in `wmk_config.yaml`.
