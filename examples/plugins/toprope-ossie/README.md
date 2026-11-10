# toprope-ossie: an extractor plugged in from outside

An example of ADR-0051's extractor port. This package reads an
[Apache Ossie](https://github.com/apache/ossie) ontology and turns it into a proposed Toprope
draft. It uses only `toprope.importers` and does not change Toprope. Its `pyproject.toml` has one
line that makes Toprope find it:

```toml
[project.entry-points."toprope.extractors"]
ossie = "toprope_ossie:OssieExtractor"
```

```bash
uv pip install -e examples/plugins/toprope-ossie
uv run toprope-import --list                  # extractors: openapi, ossie, sql, workflow
uv run toprope-import ossie examples/plugins/toprope-ossie/examples/orders.ossie.yaml --domain shop
```

## Where an Ossie ontology comes from

Any tool that exports Ossie can provide one. For example:

- **NVIDIA Auto Ontology** builds terms, facts and joins from your databases. In *Settings →
  Import / Export*, export as Apache Ossie with the ontology (or call `POST /api/model/export` with
  `format: ossie` and `include_ontology: true`). The export is a zip of three documents; give the
  ontology document to this extractor.
- **The Ossie converters** cover dbt, Snowflake, Databricks, Salesforce and others.

## What it reads, and what it asks

| Ossie | Toprope draft |
|---|---|
| `EntityType` concept | a thing (`objects.<Concept>`) |
| a relationship to a value type or a built-in | a fact, typed by the built-in it extends |
| `X == 'a' OR X == 'b'` on a string value type | an enum (every limit on the way to the built-in holds) |
| `X >= 0`, `X <= 9` on a number value type | `min`, `max` (the tightest) |
| a relationship with no other role | a boolean fact |
| a relationship to an entity type | a link (`ManyToOne` → many-to-one, `OneToOne` → one-to-one) |
| `identify_by`, `requires: [Concept.fact]` | a required fact (others are optional, as in Ossie) |
| an enum fact named in the profile's `stage_fields` | stages, with an empty matrix |

Everything else is turned into a question for the interview:
- what happens to the things, and who may do it (Ossie has no actions);
- `derived_by` concepts and facts;
- other `requires` constraints;
- relationships with three or more roles;
- facts with no multiplicity, which may have many values;
- links to ignored concepts or to `Any`.

Two source names that read as one name (`placedAt`, `placed_at`) are listed as a conflict,
naming both places. The first one is kept.

Every element stays `proposed` until a person confirms it.

Auto Ontology's certification of terms does not survive its Ossie export. A reader for its REST
API could carry it into each element's ref; that is not built yet.

`examples/flights.ontology.yaml` is Apache Ossie's own example, copied unchanged under its Apache
License 2.0 header from apache/ossie at commit d700cdea; its NOTICE is in `NOTICE`. `examples/orders.ossie.yaml` was written
for this example. `tests/test_importer_plugin_ossie.py` loads this package through the entry point
above and reads both files.
