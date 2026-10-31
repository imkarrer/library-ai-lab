# How a Student's books are found

How the assistant stores books, finds candidates, chooses what to show, and what we know is
weak. Read this before changing search, and change it when search changes.

```mermaid
flowchart TD
    subgraph Storing
        loc[Library of Congress files] -->|build_demo_catalog.py| filter[Juvenile, with a school call number]
        export[School's MARC export] -->|Catalog page| books[Books with a title and call number]
        filter --> db[(SQLite FTS5 Catalog)]
        books --> db
    end
    subgraph Answering
        q[Student's question] --> model[Answer model writes the overview]
        model --> terms[Up to 6 hidden search terms]
    end
    subgraph Finding
        terms --> strict[Each term: all its words, or nothing]
        q --> loose[Student's words: all, else any]
        strict --> turns[Take from each list in turn, one edition each]
        loose --> turns
        db --> strict
        db --> loose
        turns --> candidates[Up to 12 candidates]
    end
    subgraph Judging
        candidates --> pick[Answer model chooses, seeing the question and overview]
        model --> pick
        pick --> shown[Up to 5 books, each with a reason]
        pick -->|failed or unreadable| fallback[First 5 candidates, no reasons]
        pick -->|NONE| nothing[Nothing on this yet]
    end
```

## Storing

Each book is one row in an FTS5 table holding title, author, subjects, summary, and call
number (`library_assistant/catalog/sqlite_backend.py`). The tokenizer is FTS5's default, with
no stemming, so "wolf" does not match "wolves".

- **Demo:** Library of Congress records kept by `is_shelf_ready` (`catalog/marc.py`). Call
  numbers are built from the record's Dewey field, and a real school's may differ.
- **A school:** its MARC export, loaded whole on the Catalog page
  (`catalog/school_import.py`), under its own call numbers.

## Finding

The model's terms come from the hidden `SEARCH:` line (`prompt.py`). It's told to start with
the subject, pair the subject with what the answer talks about, and add at most one broader
subject.

`search_each` (`catalog/__init__.py`) runs each term alone with `search_strict`, then the
Student's own words with `search`, and takes one book from each list in turn.

## Ranking

Inside one search, SQLite's BM25 ranks books, with these column weights:

| Title | Subjects | Author | Summary | Id, call number |
|---|---|---|---|---|
| 10 | 5 | 2 | 1 | 0 |

After that, order is only the turn-taking. BM25 scores from different terms are not compared.

## Judging

A second, short model call sees the question, up to 1,000 characters of the overview, and each
candidate's title, author, and up to 200 characters each of subjects and summary. It answers
with numbers and one line each, or `NONE`. It can only choose from the list, so it can't invent
a book. Its reason is the model's own and can be wrong.

There's no relevance score for a shown book. BM25 only orders candidates, and the model's choice
is a yes or no with an order.

## The numbers to tune

| Setting | Value | Where |
|---|---|---|
| Search terms | 6 | `MAX_SEARCH_TERMS`, `prompt.py` |
| Candidates | 12 | `BOOK_CANDIDATES`, `routers/session.py` |
| Books shown | 5 | `MAX_BOOKS`, `prompt.py` |
| Column weights | above | `_COLUMN_WEIGHTS`, `sqlite_backend.py` |
| Rows fetched per candidate | 4 | `_ROWS_PER_RECORD`, `sqlite_backend.py` |

## What we know is weak

- **Repeatable is not correct.** The answer and choosing calls use temperature 0.3 and seed 42
  (`openai_temperature`, `openai_seed`), so one wording gets one answer, right or wrong. A
  reworded question, a new model, or a prompt change gives a different one.
- **Search depends on the overview.** Its terms come from the same reply, so a wrong overview
  aims the search at the wrong books.
- **Nothing measures quality yet.** Every change so far was judged on a handful of questions.
- **Reading level is ignored.** A picture book competes with a book for older readers.
- **No stemming, and no matching on meaning.**
- **Word matching favors what's in the record.** Many records have no summary, so the model
  judges those by title and subjects alone.

## Tried and dropped: an encyclopedia

We tested giving the answer model passages from a local copy of Simple English Wikipedia
(285,000 articles, 561 MB) to reduce wrong facts. We dropped it on 2026-10-31. To keep it,
wrong claims had to fall by about half and the first word had to arrive less than 2 seconds
later. It missed both.

The test used 80 fact questions with the real model, once with passages and once without. A
separate reviewer scored the pairs blind.

| | Without | With |
|---|---|---|
| Fully correct | 76 | 73 |
| Partly correct | 2 | 4 |
| Wrong | 2 | 3 |
| Wrong claims | 12 | 9 |
| First word, median | 0.6 s | 2.8 s |

- **Passages can mislead the model.** Asked for Wisconsin's state bird, it read the mourning
  dove article and answered "mourning dove". Without passages it said the robin, which is
  right. It also lost the stapes and Benito Juárez, and added Lake Huron to Wisconsin's Great
  Lakes.
- **It helped where nobody knows the answer.** With passages it stopped naming a rarest
  penguin and a rarest ant. The prompt rule against inventing facts already catches most of
  these.
- **Finding the right article mattered most.** The model guessed three article titles, then
  we took each article's opening and its best passages. That found the fact on 73 of 80
  questions, against 63 for plain word search. The same idea may help book search.

These questions are ours, and they are short and factual. Real research questions ask for
explanations, and the test doesn't measure those. Rerun it when we have real student
questions.
