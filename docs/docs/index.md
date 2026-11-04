# DataGEMS User Profiler Api

This is the documentation site for the DataGEMS User Profiler Api. The service is part of the wider [DataGEMS](https://datagems.eu/) platform. This is part of the overall [platform documentation](https://datagems-eosc.github.io/).

The User Profiler Api keeps a profile for each DataGEMS user: who they are, where they work, their ORCID research output and, most importantly, a set of **interest keywords**. The keywords come from two sources: the user's ORCID record, and the natural language queries they ran on the platform, from which an LLM extracts the topics they care about. Session keywords age over time, so recent interests weigh more than old ones.

Other DataGEMS services read a trimmed, portable version of the profile to personalise what they offer. For example, the [Query Recommender](https://datagems-eosc.github.io/query-recommender/) uses it to suggest the next queries:

```http
GET /user/3f2e1d4c-.../profile
Authorization: Bearer <token>
```

```json
{
  "userId": "3f2e1d4c-...",
  "keywords": ["knowledge graphs", "machine learning"],
  "weightedKeywords": [
    { "value": "knowledge graphs", "weight": 0.871, "source": "session" },
    { "value": "machine learning", "weight": 0.5, "source": "orcid" }
  ],
  "location": { "city": "Rome", "country": "Italy" },
  "affiliation": "CNR",
  "orcid": { "id": "0000-0002-1825-0097" }
}
```

You can use the menu options on the left to navigate through the available documentation. You may be interested to jump directly to an [Architecture Overview](architecture.md), see the available [Onboarding Material](onboarding.md), read about some [Api Constructs](api-overview.md), investigate how to interpret [Status & Error Codes](error-codes.md) or jump straight in to the [OpenAPI Reference](openapi.md). You can find the repository for the service here: [code repository](https://github.com/datagems-eosc/user-profiler).

For any questions, you can consult the [FAQ](faq.md), check if there is a relevant [issue](https://github.com/datagems-eosc/user-profiler/issues) answering your question or contact the [DataGEMS Help Desk](https://datagems.eu/contact-us/).
