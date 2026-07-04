# UK Parliamentary Corpus

A pipeline to extract structured UK parliamentary debate data from
[TheyWorkForYou](https://www.theyworkforyou.com/) and create yearly CSV corpora
from Hansard records.

## Output

Each yearly CSV (`Hansard_2001.csv`, `Hansard_2002.csv`, … `Hansard_2025.csv`) contains:

| Column | Description |
|---|---|
| `speaker_name` | Name of the MP or Lord speaking |
| `speaker_party` | Political party affiliation |
| `text` | Full speech block / utterance |
| `date` | Date of the debate (YYYY-MM-DD) |
| `discussion_title` | Topic or debate title |
| `chamber` | Constitutional body: "Commons" or "Lords" |
| `venue` | Physical sitting: "Main Chamber", "Westminster Hall", or "Lords Chamber" |

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
python pipeline.py --years 2001-2025 --chambers all --steps all \
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
| **download** | `download.py` | Fetches XML debate files via HTTP. Scans variants from `i` down to `a` (handling multi-variant debate files in recent years). Uses concurrent downloads. |
| **parse** | `parse.py` | Parses XML into structured `SpeechBlock` objects. Tracks `major-heading`/`minor-heading` for topic context. Handles ISO-8859-1 encoding and DTD entities. |
| **enrich** | `enrich.py` | Cross-references `speakerid` with `people.json` memberships to add party affiliation. Falls back to name-based matching (with honorific/accent normalization) when speaker IDs are missing. |
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
    ├── Hansard_2001.csv
    ├── Hansard_2002.csv
    └── ...
```

## Coverage

**2,139,598 speeches** across 25 years (2001–2025), spanning three chambers:

| Chamber | Venue | Speeches |
|---|---|---|
| Commons | Main Chamber | ~1,489,000 |
| Commons | Westminster Hall | ~200,000 |
| Lords | Lords Chamber | ~450,000 |
| **Total** | | **2,139,598** |

**Party coverage**: 98.8% (2,114,089 named parties, 25,509 Unknown).
The data spans the Blair, Brown, Cameron, May, Johnson, Truss, Sunak, and
Starmer governments, making it suitable for longitudinal political discourse
analysis.

### Known Limitations

- **~10,800 Unknowns are real people** (Earls, Bishops, some MPs) whose records
  are missing from `people.json`. The ParlParse member data does not include
  memberships for hereditary peers, bishops, and archbishops.
- **Speaker IDs missing from 2025+ XML**. All 2025 speeches lack `speakerid`
  attributes, relying entirely on name-based party matching.
- **Stephen Barclay** (934/1,194 speeches Unknown) — has a valid `speaker_id`
  but only one of his many person records maps to a membership in `people.json`.
- **Westminster Hall gaps (2002–2004, 2008–2009)**. Westminster Hall data is
  only available for 2000–2001 and 2005–2007 in the pre-2010 era, resulting in
  lower speech counts for those years.
- **Public Bill Committee (standing) debates** are not included. The `standing/` directory
  on TheyWorkForYou contains ~4,600 XML files spanning 2001–2026, but the
  pipeline does not yet download or parse them (different URL naming convention).

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
