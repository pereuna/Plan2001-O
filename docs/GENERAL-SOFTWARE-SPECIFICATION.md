# A Computer Implementation of the Olio–Object Manifesto

**General software specification — proposal 0.1 — 23 October 2026**

**Status:** Proposed architecture, not a statement of implemented behavior. This document defines **one possible computer implementation** of the independent [Finnish epistemological manifesto](OLIO-OBJEKTI-MANIFESTI.md). The manifesto supplies the philosophical distinctions; this document makes explicit engineering choices. Neither document proves a metaphysical theory.

## 1. Objective and scope

Build a computer system in which independently registered **olios** can persist before they have an assigned application meaning. Operations and relations bring these olios into contexts in which they function as **objects**. Observations produce **manifestations**. Persistent named graphs express relationships without making a directory tree, class hierarchy, or preassigned semantic type the prerequisite for existence.

This is a possible implementation, not a universal model of all physical reality. Its storage hardware, encodings, addressing widths, clocks, and execution environments are contingent engineering choices.

The design separates four questions:

1. **Existence:** what occurrence does this computer agree to preserve?
2. **Individuation:** how can a stored occurrence be distinguished from another?
3. **Relation:** what role does the occurrence occupy in a particular context?
4. **Manifestation:** what result does a specified observation procedure produce?

These questions MUST remain distinguishable in the implementation.

## 2. Terminology

| Term | Meaning in this specification |
| --- | --- |
| **Olio** (uninterpreted entity) | A separately registered, retained occurrence for which no application-level interpretation is required. Keep the Finnish word when the distinction would otherwise be lost in English. |
| **OID** | A storage-issued identifier of an occurrence within a defined scope. It is not its meaning, content hash, address in memory, or philosophical essence. |
| **Object** (relational object) | An olio participating in a particular relation or operation. This is a contextual role, not a second storage species or an OOP instance. |
| **Observation** | An event that selects an occurrence, applies an interpretation procedure within a context, and produces an observable result. |
| **Manifestation** | The result of an observation. A manifestation may be ephemeral or separately registered as an olio. |
| **Relation** | An explicitly represented association between identified occurrences in a context. |
| **Graph** | A context with explicit members and relations. A graph may be named and persisted; it need not be a tree. |
| **Carrier representation** | The implementation's concrete physical or digital representation, used to preserve and transport data but not privileged as the olio's inherent meaning. |
| **Version** | A published state of a stored occurrence. A version is not a new OID unless explicitly registered as such. |

Here **entity** is the closest conventional English word for *olio*, but alone it does not convey uninterpretedness. **Unknown object** is deliberately not used: it already presupposes the relational category and confuses absence of knowledge with absence of interpretation.

## 3. One concrete storage profile

For the first computer implementation, choose a finite digital computer and an opaque, versioned storage engine. Its internal records and transfer buffers may be sequences of eight-bit octets. **That fact describes the chosen carrier, not what every olio inherently is.** A hexadecimal display, byte length, file classification, endianness, numeric value, or character encoding is already a choice of representation or observation.

This profile may use:

- a named storage space;
- a numeric OID unique and never reused **within that space**;
- a mapping from (space identifier, OID, version) to an opaque retained carrier;
- explicit publication of revisions and recoverable committed state;
- a separate service for persistent graph relations.

An OID MUST NOT be calculated from content. Independently registered occurrences with equal carriers MUST remain individually distinguishable. The same OID MAY have several committed versions under an explicitly defined revision policy. No globally unique cross-machine identifier is assumed.

The first profile can be backed by the repository's existing GE/O storage, including its currently octet-oriented records and scoped identifiers. This is a compatibility opportunity, **not** a claim that the graph, allocation, observation, or naming APIs below already exist. Existing source and [O-FORMAT.md](O-FORMAT.md) define actual representation; [STATUS.md](STATUS.md) defines verification evidence.

A different profile could transport seven-bit symbols or digitized analogue measurements. The abstract olio model MUST NOT require that such observations be defined as eight-bit bytes. A digital backend can still encode them in octets; that encoding must be explicit at the adapter boundary.

## 4. Registration and existence

An explicit **register** operation creates a fresh stored occurrence and returns its OID. Successful durable registration establishes an **operational commitment to existence**: later operations can refer to that occurrence according to the storage contract. It does not prove observer-independent metaphysical existence.

Registration is itself an event involving the new occurrence. The occurrence thereby plays an object role **during** creation. After the event, it may have no active application-level relation or named-graph membership. Historical participation does not impose a permanent object type.

The storage bookkeeping required to retrieve a registered occurrence is not an application graph. An olio's independence means independence from **any particular semantic interpretation or application relationship**, not independence from all physical and logical implementation structure.

The registration protocol MUST define what success means and distinguish uncommitted, committed, missing, and retired occurrences. A failed registration MUST NOT silently return a reusable identifier presented as durable.

## 5. Observation and manifestation

An observation binds at least:

- the identity (and, where relevant, version) of an olio;
- an interpreter or operation;
- an explicit or default observation context;
- the resulting manifestation or error.

Conceptually:

    manifestation = observe(olio_id, interpreter, context, version)

This formula is a semantic model, not a required language-level calling convention. Selecting an OID and beginning an operation creates a temporary relation. There is no need to persist that relation merely to make an observation possible.

A basic **carrier-reader** may expose octets from this digital implementation; it is itself one interpretation. Other interpreters may expose hexadecimal text, seven-bit symbols, machine instructions, a numeric measurement, audio, or a user-interface image. The stored occurrence is not thereby permanently classified as any of these.

Two observations that display identical output establish only equality **under their stated procedures and contexts**. They do not establish that two occurrences have become one or are indistinguishable under every possible procedure.

Observation SHOULD be non-mutating by default. An operation that changes stored state MUST disclose and use explicit mutation/commit semantics. Outputs MUST distinguish the source occurrence from any independently registered resulting olio.

An observation event MAY be recorded for reproducibility, auditing, or provenance. Persistent recording MUST NOT be a prerequisite for all reads, and the system MUST NOT silently attach a global type or application metadata record as a side effect of observation.

## 6. Named persistent graphs

Graphs are a separate layer for relationships and discovery. A graph has an identifier, optional names, explicit member occurrences, and explicit relations between occurrences. A graph MAY have isolated members without edges. Several graphs MAY refer to the same OID with different meanings.

For this particular implementation, choose the minimal relation shape:

    (graph_id, subject_oid, predicate_oid, object_oid)

The predicate itself refers to a registered olio, allowing predicate interpretation and naming to remain contextual. Graph membership is represented explicitly, independently of edge participation. Implementations MAY optimize predicates with tokens or indexes without making human-readable labels fundamental types.

**Object** in the fourth field names a relation endpoint in this notation. It does not mean that other occurrences are non-objects. Every olio participating in the relation has an object role within that context.

A graph's name is a binding, not a canonical path or part of the members' identity. Names are allowed to be contextual, plural, and changeable. A hierarchical namespace MAY be constructed as a graph interpretation; no root directory, single parent, or pathname is required by the model.

Removing a relation or a whole graph MUST NOT silently delete the olio occurrences it referred to. Reachability from graphs is not a universal definition of existence. Explicit retirement and any storage reclamation policy remain separate operations.

Graphs MAY refer to code, provenance, contextual roles, or other graphs through named occurrences. No global, compulsory class hierarchy or complete metadata schema is assumed.

## 7. Types, files, programs and language boundaries

A **type** constrains valid interpretation or operations within a context. A **class** can be an explicitly defined or query-derived collection. Neither is a prerequisite for registering an olio.

A **file** is one practical digital interpretation or transport abstraction, often an ordered sequence of octets. It is not the universal substance of stored olio occurrences. Code, images, text, and files can all be recognized through interpretation and relations.

Executing content is a specialized observation/action process involving validation, architecture selection, execution context, and effects. Stored source or executable material MUST NOT become intrinsically an executable by having a particular OID or by being stored as octets.

A language runtime (including Python) MAY provide convenient wrappers, classes, imports, and attributes. Its own object model MUST NOT silently become the native ontology, persistent graph semantics, or required on-disk class tree.

## 8. Events, histories and provenance

Do not conflate the following:

- registration of an occurrence in this computer;
- creation of source material elsewhere;
- import or copying of a carrier;
- publication of a new revision;
- observation of a revision;
- production or registration of a manifestation.

These are different events. A timestamp is an observation by a particular clock under a stated trust model, not a magically true historical fact. If original creation time is not known, it MUST remain **unknown**, not be replaced by import time.

A deployment MAY retain event records as separately identified occurrences or graph relations. It MUST NOT make Unix-style owner, mode, creation time, modification time, or pathname compulsory philosophical properties of every olio.

Where timestamps or provenance are recorded, their event type, source, and uncertainty SHOULD be distinguishable.

## 9. Abstract operations

The following describe **proposed semantics**, not implemented function signatures, ABI promises, or specific kernel system calls.

| Operation | Effect |
| --- | --- |
| **register(space, carrier)** | Allocate a fresh OID and durably publish a new uninterpreted occurrence. |
| **retrieve(space, oid, version?)** | Obtain the chosen profile's opaque carrier from a consistent published version. |
| **revise(space, oid, carrier)** | Publish a new version of the same occurrence, without changing its OID. |
| **observe(oid, interpreter, context, version?)** | Form an ephemeral observation relation and return a manifestation. |
| **create_graph(name?)** | Create an independent graph context, optionally with a name binding. |
| **add_member(graph, oid)** | Make an occurrence a member without requiring an edge. |
| **relate(graph, source, predicate, target)** | Add a persistent contextual relation; do not assign a universal class. |
| **query(graph, pattern)** | Return relations or members under the graph's own context. |
| **retire(oid)** | Explicitly mark an occurrence no longer retrievable under the chosen retention policy. |

Retrieval MUST NOT implicitly register a missing OID. Querying relations MUST NOT require changing the underlying occurrence. Invalid IDs and forbidden operations MUST produce explicit errors. The exact authorization, concurrency, deletion, retention, and crash guarantees are to be stated by the implementation profile, not guessed from the philosophy.

## 10. Consistency and resource boundaries

The computer implementation MUST specify atomicity and visibility of publication for both occurrence revisions and graph updates. It SHOULD offer a stable observation of a selected published version so an interpreter cannot accidentally combine parts of different revisions.

Relations MUST refer to distinguishable occurrences under a documented scope. Cross-space or remote references require explicit resolution rules, not accidental integer collisions.

A finite implementation needs explicit quotas, memory limits, resource ownership, failure recovery, and authorization. These mechanisms MAY use internal tags or structured records without treating their engineering format as metaphysical categories.

A temporary operation relation may disappear after execution. A durable graph change requires an explicit publication event. Security decisions MUST NOT be based solely on a human-readable semantic label such as “file” or “compiler”.

## 11. Illustrative scenario

1. An importer registers a retained carrier as OID 1, without assigning it a universal type.
2. A second independent registration of an equal carrier receives OID 2. Equality under one reader does not merge the occurrences.
3. A text interpreter observes OID 1 and produces one manifestation. A hexadecimal renderer observes the same OID and produces another.
4. A named graph contains OID 1 and relates it to an interpreter, purpose, or provenance occurrence. This makes OID 1 an object in that context without altering its stored carrier.
5. Deleting the graph binding removes the contextual description. OID 1 remains registered until explicitly retired.
6. The system can recover OID 1 after a restart even though no application graph is needed merely to preserve it.

The words **text** and **hexadecimal** in step 3 name interpreters; they do not assert that the original olio was inherently a text file or a sequence of hexadecimal numbers.

## 12. Architectural constraints and non-goals

- MUST distinguish occurrence identity, carrier, interpreter, observation, and manifestation.
- MUST preserve separately registered occurrences even if a chosen interpretation says they are equal.
- MUST allow occurrences without any persistent application-graph membership.
- MUST support independent contextual graphs without requiring a directory tree or class inheritance.
- MUST NOT treat eight-bit bytes, OOP instances, or one universal taxonomy as the definition of existence.
- MUST NOT infer an original creation timestamp from copying or import.
- MUST NOT confuse a proven implementation property with philosophical certainty.
- SHOULD permit temporary observation without persistent relation writes.
- MAY use familiar files, octets, streams, numeric OIDs, and code execution as explicit computer-interface choices.

This specification does **not** require an analogue computer, solve the philosophical problem of other minds or external reality, define a universal logic of all possible self-reference, or prescribe a network protocol, GUI, process scheduler, or programming language.

## 13. Relationship to the existing proof of concept

The repository's current O profile already offers useful **engineering substrates**: scoped OIDs, versioned opaque octet payloads, and a functioning persistent execution experiment. It does not yet have a general OID allocator, persistent native relation graphs, or an observation API with the semantics above. The existing Python persistence graph is not the proposed independent named-graph layer.

Accordingly:

- [O-FORMAT.md](O-FORMAT.md) documents implemented storage facts.
- [STATUS.md](STATUS.md) documents demonstrated behavior and tests.
- [OBJECT-MODEL.md](OBJECT-MODEL.md) records the earlier byte-file-centered architecture; where its philosophical assertions differ, this document is the **new proposed conceptual direction**, not evidence of an implementation change.
- [OLIO-OBJEKTI-MANIFESTI.md](OLIO-OBJEKTI-MANIFESTI.md) is the independent philosophical foundation.

Future implementation changes require separate technical design, code, and verification. No new API, graph index, storage migration, or disk-format revision is authorized merely by publishing this proposal.

---

**Design thesis:** The computer commits to preserving individually registered occurrences. Interpretation makes an occurrence an object in a context; observation yields a manifestation; persistent graphs make selected relationships durable. **The implementation may use bytes, but existence is not defined as bytehood.**
