<img src="https://raw.githubusercontent.com/trois-dev/trois/main/Design/Icon/TroisIcon.svg" width="96" alt="Trois logo">

# Trois Themes

Window themes from classic customizers like EppieDesktop and Kaleidoscope, ready to install in [Trois](https://github.com/trois-dev/trois).

The gallery is at https://trois-dev.github.io/trois-themes/. Install opens Trois, downloads the theme and applies it. Trois can also browse and install these from Settings > Gallery.

To get Trois, download the zip from [Trois releases](https://github.com/trois-dev/trois/releases), unzip it, move Trois.app to Applications and give it Accessibility permission when asked. It needs macOS 13 or later on Apple silicon.

## Credits

Each theme is the work of the author named in its `theme.json`. `engine` names the tool it was made for and `source` links to where it was collected. Themes are rehosted here unmodified, with their original readmes, so they keep working with Trois. See the [Trois credits](https://github.com/trois-dev/trois#credits) for the archives they were collected from.

If you made one of these themes and want it credited differently or taken down, open an issue and it will be handled promptly.

## Submitting a theme

The easy way: [open a submission](https://github.com/trois-dev/trois-themes/issues/new?template=submit_theme.yml), fill in the name and author, and attach a zip. A maintainer reviews it, then a bot opens a pull request that adds it, credited to you. If you're comfortable with git, open a pull request yourself as described below.

## Adding a theme

1. Add a folder under `themes/`. Its name is the theme's id: letters, digits, `-` or `_`.
2. Put the button images in it (BMP, PNG, JPEG, GIF, TIFF or ICO, each under 1 MB), plus any readme.
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

   Button keys: `close`, `closeHover`, `closeDown`, `closeDisabled`, `minimize`, `minimizeHover`, `minimizeDown`, `minimizeDisabled`, `zoom`, `zoomHover`, `zoomDown`, `zoomDisabled`, `restore`, `restoreDown`, `help`, `helpHover`, `helpDown`, `helpDisabled`. At least one of `close`, `minimize` or `zoom` is required.

   `description`, `engine` and `source` are optional. `description` is a short blurb shown when you hover the theme; use `\n` for line breaks. Kaleidoscope schemes carry the one their author wrote for the control panel. `engine` is the tool the theme was made for, such as `EppieDesktop`, `Kaleidoscope 1.x` or `Kaleidoscope 2.x`; leave it out for themes made for Trois. `source` is a URL for the original download or gallery.

4. Run the check described in [CONTRIBUTING](CONTRIBUTING.md#adding-a-theme-with-a-pull-request) and open a pull request.

To update a theme, change its files and raise `version`. Trois offers the update to people who installed it.
