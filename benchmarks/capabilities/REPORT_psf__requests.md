# PyCodeKG Capability Report — `psf__requests`

Structural queries a vector index cannot answer in principle, and `grep` answers imprecisely. All figures below are computed from the AST graph — deterministic, no LLM, no embedding similarity.

- Graph: 6739 nodes, 13161 edges (1812 `CALLS`), 651 functions/methods.

> **Honesty caveat.** PyCodeKG's Python call graph resolves method calls by *name* (no type inference). For a method name shared across many classes (e.g. `get`), the caller set is an **over-approximation** — the same failure mode as `grep`. The graph's clean, exact wins are for *uniquely-named* symbols (below) and for the *aggregate* views (dead-code set, fan-in distribution) that no embedding can produce at all. Names that collide are flagged in the table.


## 1. Change blast-radius — highest fan-in functions

*"If I touch this, what might break?" — ranked by `CALLS` in-degree. A similarity search has no notion of this at all.*


| rank | function | fan-in | module | name shared by |
|---:|---|---:|---|---:|
| 1 | `CaseInsensitiveDict.get` | 124 | `requests/structures.py` | 5 defs ⚠️ |
| 2 | `LookupDict.get` | 124 | `requests/structures.py` | 5 defs ⚠️ |
| 3 | `RequestsCookieJar.get` | 124 | `requests/cookies.py` | 5 defs ⚠️ |
| 4 | `Session.get` | 124 | `requests/sessions.py` | 5 defs ⚠️ |
| 5 | `get` | 124 | `requests/api.py` | 5 defs ⚠️ |
| 6 | `httpbin` | 45 | `tests/test_requests.py` | unique ✓ |
| 7 | `CharDistributionAnalysis.__init__` | 39 | `requests/packages/chardet2/chardistribution.py` | 68 defs ⚠️ |
| 8 | `PoolError.__init__` | 35 | `requests/packages/urllib3/exceptions.py` | 68 defs ⚠️ |

## 2. Dead code — functions/methods with zero callers (235)

*Computed from in-degree on `CALLS`. (Entry points, dynamically-dispatched, test, and public-API functions are expected false positives — but every genuinely-dead function is in this list, which no embedding can produce.)*

- `AuthBase.__call__`  ·  `requests/auth.py`
- `Big5DistributionAnalysis.get_order`  ·  `requests/packages/chardet2/chardistribution.py`
- `CaseInsensitiveDict.__contains__`  ·  `requests/structures.py`
- `CharDistributionAnalysis.get_order`  ·  `requests/packages/chardet2/chardistribution.py`
- `Client._add_bearer_token`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client._add_mac_token`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.add_token`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.parse_request_body_response`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.parse_request_uri_response`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.prepare_refresh_body`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.prepare_request_body`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `Client.prepare_request_uri`  ·  `requests/packages/oauthlib/oauth2/draft25/__init__.py`
- `ConnectionPool.__str__`  ·  `requests/packages/urllib3/connectionpool.py`
- `CookieTests.test_convert_jar_to_dict`  ·  `tests/test_cookies.py`
- `CookieTests.test_cookies_from_response`  ·  `tests/test_cookies.py`
- … and 220 more

## 3. "Who calls X?" — PyCodeKG vs grep

Target: `httpbin` in `tests/test_requests.py`


**PyCodeKG: 45 caller(s)** — exact, scope- and import-alias-resolved:

- `tests/test_requests.py::RequestsTestSuite.test_HTTP_200_OK_GET`
- `tests/test_requests.py::RequestsTestSuite.test_response_sent`
- `tests/test_requests.py::RequestsTestSuite.test_HTTP_302_ALLOW_REDIRECT_GET`
- `tests/test_requests.py::RequestsTestSuite.test_HTTP_302_GET`
- `tests/test_requests.py::RequestsTestSuite.test_HTTP_200_OK_GET_WITH_PARAMS`
- `tests/test_requests.py::RequestsTestSuite.test_user_agent_transfers`
- `tests/test_requests.py::RequestsTestSuite.test_HTTP_200_OK_HEAD`
- `tests/test_requests.py::RequestsTestSuite.test_HTTP_200_OK_PUT`

**grep `\bhttpbin\s*\(`: 98 textual hit(s)** — and grep cannot tell which are calls:

- 1 are the definition line(s)
- 98 are in test files
- 20 are comment/docstring/string lines
- plus every unrelated method that shares the name, and **zero** of the calls made through an import alias (which grep can't follow).

> This is the article's own criticism of vector search — *"semantic similarity isn't structural relevance; `processPayment` vs `handlePayment` needs exact resolution"* — turned back on `grep`: textual matching isn't call resolution either. Only the graph resolves the call.

