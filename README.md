# UK Parliamentary Corpus

A pipeline to extract structured UK parliamentary debate data from
[TheyWorkForYou](https://www.theyworkforyou.com/) and create yearly CSV corpora
from Hansard records.

## Output

Each yearly CSV (`Hansard_2010.csv`, `Hansard_2011.csv`, etc.) contains:

| Column | Description |
|---|---|
| `speaker_name` | Name of the MP or Lord speaking |
| `speaker_party` | Political party affiliation |
| `text` | Full speech block / utterance |
| `date` | Date of the debate (YYYY-MM-DD) |
| `discussion_title` | Topic or debate title |
| `chamber` | Commons, Lords, or Westminster Hall |

## Data Source

Debate transcripts are sourced from the TheyWorkForYou
[scrapedxml archive](https://www.theyworkforyou.com/pwdata/scrapedxml/),
maintained by [mySociety](https://www.mysociety.org/) via the
[ParlParse](https://github.com/mysociety/parlparse) project.

Speaker party affiliations come from `people.json` (Popolo format) in the
ParlParse [members directory](https://github.com/mysociety/parlparse/tree/master/members).

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/Water1ock/UK-Parliamentary-Corpus.git
cd UK-Parliamentary-Corpus
pip install -r requirements.txt
```

### 2. Download member lookup data

```bash
mkdir -p members
curl -L -o members/people.json \
  https://github.com/mysociety/parlparse/raw/master/members/people.json
```

> **Note:** `people.json` is ~5 MB and contains all MPs and Lords with party
> affiliations in Popolo format. It is gitignored by default.

### 3. Run the pipeline

```bash
# Full pipeline: download, parse, enrich, export
python pipeline.py --years 2010-2020 --chambers all --steps all \
    --members-file ./members/people.json

# Download only
python pipeline.py --years 2010,2011 --chambers commons,lords --steps download

# Parse and export from existing downloads
python pipeline.py --years 2010 --chambers commons --steps parse,enrich,export \
    --members-file ./members/people.json
```

## Pipeline Steps

The pipeline runs in four sequential steps:

| Step | Script | Description |
|---|---|---|
| **download** | `download.py` | Fetches XML debate files via HTTP. Tries the authoritative 'b' variant first, falling back to 'a'. Uses concurrent downloads. |
| **parse** | `parse.py` | Parses XML into structured `SpeechBlock` objects. Tracks `major-heading`/`minor-heading` for topic context. Handles ISO-8859-1 encoding and DTD entities. |
| **enrich** | `enrich.py` | Cross-references `speakerid` with `people.json` memberships to add party affiliation. |
| **export** | `export.py` | Groups speeches by year and exports `Hansard_YYYY.csv` files with full CSV quoting. |

Saves interim JSON after parse and enrich steps for restartability.

## Directory Structure

```
UK-Parliamentary-Corpus/
├── pipeline.py          # Main orchestrator (CLI entry point)
├── download.py          # XML downloader (concurrent HTTP)
├── parse.py             # XML parser (lxml-based)
├── enrich.py            # Party lookup (Popolo people.json)
├── export.py            # CSV exporter
├── requirements.txt     # Python dependencies
├── README.md
├── .gitignore
├── members/
│   └── people.json      # Member lookup (download separately)
├── data/                # Downloaded XML files (gitignored)
│   ├── debates/         # Commons debates
│   ├── lordspages/      # Lords debates
│   └── westminhall/     # Westminster Hall debates
└── output/              # Generated CSVs (gitignored)
    ├── Hansard_2010.csv
    ├── Hansard_2011.csv
    └── ...
```

## Coverage

- **Commons debates**: 2001–present (~200 sitting days/year)
- **Lords debates**: 1999–present
- **Westminster Hall debates**: 1999–present

The data spans the Blair, Brown, Cameron, May, Johnson, Truss, Sunak, and Starmer
governments, making it suitable for longitudinal political discourse analysis.

## License & Attribution

The debate XML is provided by TheyWorkForYou under the
[Open Parliament Licence](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).

Please cite:
> TheyWorkForYou / mySociety ParlParse project. "UK Parliamentary Hansard (scrapedxml)."
> https://parser.theyworkforyou.com/

## Related Projects

- [ParlParse](https://github.com/mysociety/parlparse) — the upstream parser
- [TheyWorkForYou](https://www.theyworkforyou.com/) — parliamentary monitoring
- [PublicWhip](https://www.publicwhip.org.uk/) — voting record analysis
- [Popolo standard](https://www.popoloproject.com/) — civic data format
