# MK static site generator

## Running process_pages.py

1. Mako templates (in `templates/`) are loaded and any templates ending with the extension `.mhtml` and NOT starting with an underscore or containing `base` in the filename are processed into html and written into the output directory (`htdocs/`) at the corresponding location and under the same file names (except that `.mhtml` is of course changed into `.html`).

2. Markdown content in `content/` is loaded and rendered to the corresponding place in `htdocs/` using the template specified in the metadata section of the file (`md_base.mhtml` being the default template). The HTML produced by converting the markdown source is in the `CONTENT` template variable.

3. Any static files in `static/` are rsynced into `htdocs/`. Note that you should be careful not to overwrite files produced by the previous two steps.

4. The asset pipeline is run. Currently this only compiles `.scss` files into CSS and places the result in `htdocs/css/`.

## Metadata in Markdown files

Currently there are only two special variables in the metadata section:

- `template`: Filename of Mako template from `templates/` directory. The default is `md_base.mhtml`.

- `pretty_path`: If this is false, the output filename in `htdocs/` will be the same as the path of the source inside `content/` except with an extension of `.html` instead of `.md`. If it is true, the output path will consist of the input except that the extension `.md` is replaced with `/index.html` (i.e. the file basename is turned into a directory name). The default value is true.
