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
| `venue` | Physical sitting: "Main Chamber", "Westminster Hall", "Lords Chamber", or "Public Bill Committee" |

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
│   ├── westminhall/     # Westminster Hall debates
│   └── standing/        # Public Bill Committee debates
└── output/              # Generated CSVs (gitignored)
    ├── Hansard_2001.csv
    ├── Hansard_2002.csv
    └── ...
```

## Coverage

**2,504,534 speeches** across 25 years (2001–2025), spanning four venues:

| Chamber | Venue | Speeches |
|---|---|---|
| Commons | Main Chamber | ~1,280,000 |
| Commons | Westminster Hall | ~210,000 |
| Commons | Public Bill Committee | ~365,000 |
| Lords | Lords Chamber | ~650,000 |
| **Total** | | **2,504,534** |

**Party coverage**: 98.9% (2,477,720 named parties, 26,814 Unknown).
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
- **Westminster Hall gaps (2002–2004)**. Westminster Hall data is genuinely
  absent for 2002–2004 (all probed dates return 404). 2008–2009 has spottier
  coverage (some dates available, some not), resulting in lower speech counts.
- **Public Bill Committee speaker IDs missing post-2015**. Standing files from
  2015 onwards (both standard and bill-ID-named files) lack `speakerid`
  attributes, so party matching for these speeches relies entirely on
  name-based fallback matching. This affects ~91,000 speeches but party
  coverage remains strong (name matching handles most MPs).
- **Employment Rights Bill 2024–25 (bill 3737)**: The corpus now contains all stages.
  Commons Public Bill Committee (26 Nov 2024 – 16 Jan 2025, 21 sessions,
  1,673 speeches) is present under the "Public Bill Committee" venue, with
  generic discussion titles ("Public Bill Committee"). The committee files
  were discovered on the server under bill-ID naming
  (`standing5339_EMPLOYMENT_...`).

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
