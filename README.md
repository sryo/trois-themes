# Trois Themes

Button themes for [Trois](https://github.com/sryo/trois), an homage to EppieDesktop by Jeff Epstein.

The gallery is at https://sryo.github.io/trois-themes/. Install opens Trois, downloads the theme and applies it. Trois can also browse and install these from Settings > Get Themes.

## Credits

Each theme is the work of the author named in its `theme.json`. Most were first collected in the [Virtual Plastic Eppie gallery](https://www.virtualplastic.net/html/eppie.html) and are rehosted here unmodified, with their original readmes, so they keep working with Trois.

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

4. Check it with `python3 scripts/build.py --check` (needs `pip install pillow`) and open a pull request.

To update a theme, change its files and raise `version`. Trois offers the update to people who installed it.

## How the catalog is built

`scripts/build.py` checks every theme and writes `site/`: one zip per theme with fixed timestamps, so its SHA-256 only changes when the files do, PNG previews, `index.json` and the gallery page. The workflow in `.github/workflows/pages.yml` runs it on every pull request and publishes `site/` to GitHub Pages from `main`.

Trois only installs themes listed in `index.json`, checks each download against its SHA-256 and size, and rejects zips with symlinks, paths outside the theme folder or other file types.
