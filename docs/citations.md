# Citation System

## Generation

From actual source metadata (`document.doc_metadata`): authors, title, journal/conference, year, DOI, volume/issue/pages. Never fabricates missing fields — uses "Metadata unavailable" placeholder and notes incomplete.

Styles:

- **APA 7**: `Author (Year). Title. Journal, Volume, Pages. https://doi.org/...` or `[No DOI/journal metadata available]` if missing.
- **IEEE**: `Author, "Title," Journal, Year. doi: ...`
- **MLA**: `Author. "Title." Journal, Year. DOI: ...`

Endpoint: `GET /api/learning/citations/{document_id}?style=apa|ieee|mla`

Example response:

```json
{
  "document_id": "abc",
  "style": "apa",
  "formatted": "Rowe, D.M. (2018). Thermoelectrics Handbook. CRC Press.",
  "metadata": {"title": "...", "authors": "Rowe, D.M.", "year": "2018", "doi": null},
  "complete": false,
  "note": "Metadata incomplete — citation uses available information only"
}
```

## Provenance per Citation

```json
{
  "type": "source",
  "document": "thermoelectric-paper.pdf",
  "page": 7,
  "section": "Results",
  "chunk_id": "...",
  "source_text": "The electrical output increased by...",
  "retrieval_score": 0.34,
  "citation_metadata": {"heading_hierarchy": "3. Results", "content_type": "result"}
}
```

## UI

Click citation chip → modal shows Document/Page/Section/Original Context around evidence, not forcing user to search entire document.

## Source Quality

Categories: peer-reviewed paper, textbook, university material, government source, lab manual, personal notes, dataset, unknown. Heuristic: abstract+references → peer-reviewed; "lab manual" in filename → lab manual; .csv → dataset.

Do not assume PDF is trustworthy solely because it is PDF.
