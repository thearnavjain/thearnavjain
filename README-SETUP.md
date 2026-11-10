# Animated GitHub profile README

This folder is the ready-to-push contents of the `thearnavjain/thearnavjain` profile repository. The repository name must match the GitHub login exactly for GitHub to use its README on the profile page.

The visual system follows [arnavjain.io](https://arnavjain.io): warm paper `#F4F4F9`, ink `#252227`, muted blue `#4C5573`, terracotta `#895A4E`, and the site's Instrument Serif, Inter, and IBM Plex Mono fonts. The script subsets those fonts with `pyftsubset` and embeds the resulting WOFF files in each SVG.

## Preview

From this folder, install FontTools and render a fixed final frame:

```powershell
python -m pip install fonttools
$env:STATIC = "1"
python build_cards.py --refresh-data
```

`STATIC=1` is also accepted as an environment variable in other shells. Omit it to regenerate the animated cards. Contribution history is read from `data/contributions.json`; `--refresh-data` updates that file from GitHub's public contribution calendar first.

## Publish

The repository is public so GitHub can display this profile README. GitHub Actions refreshes contribution data and commits rendered SVG cards every day at 05:23 UTC. It uses only the built-in `GITHUB_TOKEN` write permission and does not need a personal access token.
