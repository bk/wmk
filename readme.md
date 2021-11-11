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

```
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
  the content base directory. E.g. `wmk info .`.

- `wmk run $basedir`: Compiles/copies files into `$basedir/htdocs`.

- `wmk watch $basedir`: Watches for changes in the source directories inside
  `$basedir` and recompiles if changes are detected.

- `wmk serve $basedir`: Serves the files in `$basedir/htdocs` on
  `http://localhost:7007/`.

## File organization

Inside a given working directory, `wmk` assumes the following subdirectories for
content and output. They will be created if they do not exist:

- `htdocs`: The output directory. Rendered, processed or copied content is
  placed here, and `wmk serve` will serve files from this directory.

- `templates`: Mako templates. Templates with the extension `.mhtml` are
  rendered directly into `htdocs` as `.html` files, unless their filename starts
  with a dot or underscore or ends with `base.mhtml`.

- `content`: Markdown content with YAML metadata. This will be rendered into
  html using the `template` specified in the metadata or `md_base.mhtml` by
  default. The target filename will be `index.html` in a directory corresponding
  to the basename of the markdown file, unless `pretty_path` in the metadata is
  `false` (in which case only the extension is replaced). The converted content
  will be passed to the Mako template as a string in the context variable
  `CONTENT`, along with other metadata. A YAML datasource can be specified in
  the metadata block as `LOAD`; the data in this file will be added to the
  context.

- `data`: YAML files for additional metadata.

- `assets`: Assets for an asset pipeline. Currently this only handles SCSS/Sass
  files in the subdirectory `scss`. They will be compiled to CSS which is placed
  in the target directory `htdocs/css`.

- `static`: Static files. Everything in here will be rsynced directoy over to
  `htdocs`.

## Notes

* The order of operations is as follows:

  1. Copy files from `static/`.
  2. Run asset pipeline.
  3. Render Mako templates from `templates`.
  4. Render Markdown content from `content`.

  Note that later steps may overwrite files placed by earlier steps.

* `wmk.py` uses timestamps to prevent unnecessary re-rendering of templates,
  markdown files and scss sources. The check is rather primitive so it may be
  necessary to touch the main source file or remove files from `htdocs` in order
  to trigger a refresh.

* If files are removed from source directories the corresponding files in
  `htdocs` will not disappear automatically. You have to clear them out
  manually.

## Config file

A config file, `$basedir/wmk_config.yaml`, can be used to configure some aspects
of how `wmk` operates. Currently there is support for the following settings:

- `template_context`: Default values for the context passed to Mako templates.
  This should be a dict. The values may be overridden by markdown metadata or
  linked YAML files.

- `shortcodes`: A way to easily embed content such as YouTube videos os Github
  gists into your Markdown. See further below.

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

[ext]: https://python-markdown.github.io/extensions/
[other]: https://github.com/Python-Markdown/markdown/wiki/Third-Party-Extensions

## Shortcodes

A shortcode consists of an opening tag, `{{<`, followed by any number of spaces,
followed by a string representing the "short version" of the content, followed
by any number of spaces and the closing tag `>}}`. It should stay on one line.
Here is an example:

```
{{< youtube p118YbxFtGg >}}
```

The value of the `shortcodes` section of the config file should be a dict where
the key is an identifier for the type of shortcode and the value should be a
dict with two keys, `pattern` and `content`. The pattern is a regular expression
and the content is substituted for the string which the regular expression
matches. Here is a working example:

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

When applied to the above shortcode, this results in

```html
<div class="video-container"><iframe width="560" height="315" src="https://www.youtube.com/embed/p118YbxFtGg" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
```

Shortcodes are applied **before** the Markdown document is converted to HTML, so
it is possible to replace a shortcode with Markdown content which will then be
processed normally.

Currently no default shortcodes are provided. In order to use them, they must be
added to `wmk_config.yaml`.
