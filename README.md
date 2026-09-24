# Trois Themes

Window themes from classic customizers like EppieDesktop and Kaleidoscope, ready to install in [Trois](https://github.com/trois-dev/trois).

The gallery is at https://trois-dev.github.io/trois-themes/. Install opens Trois, downloads the theme and applies it. Trois can also browse and install these from Settings > Get Themes.

## Credits

Each theme is the work of the author named in its `theme.json`. `engine` names the tool it was made for and `source` links to where it was collected. Themes are rehosted here unmodified, with their original readmes, so they keep working with Trois. See the [Trois credits](https://github.com/trois-dev/trois#credits) for the tools and archives they come from.

If you made one of these themes and want it credited differently or taken down, open an issue and it will be handled promptly.

## Adding a theme

1. Add a folder under `themes/`. Its name is the theme's id: letters, digits, `-` or `_`.
2. Put the button images in it (BMP, PNG, JPEG, GIF or TIFF, each under 1 MB), plus any readme.
3. Add a `theme.json`:

   ```json
   {
     "name": "My Theme",
     "author": "Your Name",
     "version": 1,
     "engine": "EppieDesktop",
     "source": "https://example.com/where-it-came-from",
     "buttons": {
       "close": "close_up.png",
       "closeDown": "close_down.png",
       "minimize": "min_up.png",
       "minimizeDown": "min_down.png",
       "zoom": "max_up.png",
       "zoomDown": "max_down.png"
     }
   }
   ```

   Button keys: `close`, `closeDown`, `closeDisabled`, `minimize`, `minimizeDown`, `minimizeDisabled`, `zoom`, `zoomDown`, `zoomDisabled`, `restore`, `restoreDown`, `help`, `helpDown`. At least one of `close`, `minimize` or `zoom` is required.

   `engine` and `source` are optional. `engine` is the tool the theme was made for, such as `EppieDesktop`, `Kaleidoscope 1.x` or `Kaleidoscope 2.x`; leave it out for themes made for Trois. `source` is a URL for the original download or gallery.

4. Check it with `python3 scripts/build.py --check` (needs `pip install pillow`) and open a pull request.

To update a theme, change its files and raise `version`. Trois offers the update to people who installed it.

## How the catalog is built

`scripts/build.py` checks every theme and writes `site/`: one zip per theme with fixed timestamps, so its SHA-256 only changes when the files do, PNG previews, `index.json` and the gallery page. The workflow in `.github/workflows/pages.yml` runs it on every pull request and publishes `site/` to GitHub Pages from `main`.

Trois only installs themes listed in `index.json`, checks each download against its SHA-256 and size, and rejects zips with symlinks, paths outside the theme folder or other file types.
