# Contributing themes

Anyone can add a theme to the catalog. New themes you made yourself and classic themes rescued from old archives are both welcome.

## Submitting without git

[Open a submission](https://github.com/trois-dev/trois-themes/issues/new?template=submit_theme.yml) and attach your theme as a zip. A maintainer reviews it and adds the `import` label. A bot then checks the zip and opens a pull request, with you credited on the commit. If something's wrong, the bot comments on your issue. Edit the issue to fix it and a maintainer will run the import again.

## Adding a theme with a pull request

Follow [Adding a theme](README.md#adding-a-theme) in the README. In short:

1. Fork this repo and add a folder under `themes/` with your images and a `theme.json`.
2. Run the check locally:

   ```bash
   pip install pillow
   python3 scripts/build.py --check
   ```

3. Open a pull request. The same check runs on every PR. Once it's merged the theme shows up in the gallery and in Trois.

To preview it in the app before submitting, drop the folder onto Settings > Themes in Trois.

## Rules

- **Credit the author.** Put the original author in `author`, even if you only converted it. Use `source` to link where it came from.
- **Keep old themes as they are.** Themes from other tools are rehosted unmodified, with their original readmes. If a conversion needs changes, say what you changed in the PR.
- **Only allowed file types.** Images (BMP, PNG, JPEG, GIF, TIFF, ICO), plus `txt`, `json`, `3dc`, `ccs` and `reg`. Each file must be under 1 MB and the zipped theme under 2 MB. The check enforces this.
- **Nothing offensive,** and nothing you don't have the right to share.

## Updating a theme

Change its files and raise `version` in `theme.json`. Trois offers the update to people who installed it. If you aren't the author, explain why in the PR.

## Credits and takedowns

If you made a theme here and want it credited differently or removed, open an issue with the "Credit or takedown" template. It will be handled promptly.
