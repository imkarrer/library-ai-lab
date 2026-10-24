# Supervised use, not whole-school self-serve

Prefill is serialized on one machine and shared by everyone: at ~6,000 prompt tokens per
grounded query and ~2,700 tok/s prefill on an M5 Max, 25 simultaneous askers wait ~55 s for
a first token. Prefix caching and top-4 retrieval cut that roughly 60%, and a supervised class
has 4-6 requests in flight, which one box serves well. Whole-school self-serve (30-60 in
flight) does not fit on one machine, so it is out of scope until real Install data argues
otherwise. Prefer mixture-of-experts models with small active-parameter counts: on M5 Max a
35B-A3B prefills ~6x faster than a dense 27B, and perceived speed depends more on that than
on anything else.
