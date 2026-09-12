[![Tests](https://github.com/DataShades/ckanext-tables/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-tables/actions/workflows/test.yml)
[![Coverage Status](https://coveralls.io/repos/github/DataShades/ckanext-tables/badge.svg?branch=master)](https://coveralls.io/github/DataShades/ckanext-tables?branch=master)

# ckanext-tables

A CKAN extension to display tabular data in a nice way using [Tabulator](http://tabulator.info/).

See the [documentation](https://datashades.github.io/ckanext-tables/) for more information.

!["Rendered Table Example"](https://github.com/DataShades/ckanext-tables/blob/master/docs/image/usage_result.png)

## Development

The frontend TypeScript/SCSS is compiled and committed to the repo by hand — there is no build step in CI, so run these and commit the results whenever you change anything under `ckanext/tables/assets/`:
```sh
npm install
npm run ts-build   # compiles + minifies the TS into tables-tabulator.js
npm run build      # compiles SCSS into CSS
```

## Tests

To run the tests, do:
```sh
pytest --ckan-ini=test.ini
```

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
