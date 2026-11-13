# Vocab frontend source

Edit static browser assets here; server templates remain in `../templates/`. `styles/layout.css` owns Vocab-specific layouts and `styles/app.css` owns domain styles.

From My Boy, run `npm run web:build -- --app vocab` or `npm run design:sync` for all three apps. Generated assets are served from `../static/`; do not edit those outputs directly. Keep source and output changes in Vocab's own repository. The generated app runs independently of My Boy's server.
