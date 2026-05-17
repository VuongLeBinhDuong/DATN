// Custom KG schema for graph-first KG-RAG (coexists with GraphRAG-import schema).
//
// Nodes:
//   (:Document {doc_id, title, source, created_at})
//   (:Chunk {chunk_id, doc_id, text, section_path, start_offset, end_offset, embedding, embedding_model, created_at})
//   (:Entity {entity_id, canonical_name, type, aliases, created_at})
//
// Relationships:
//   (d:Document)-[:HAS_CHUNK]->(c:Chunk)
//   (c:Chunk)-[:MENTIONS {confidence, start_char, end_char}]->(e:Entity)
//   (a:Entity)-[:REL {predicate, confidence, evidence_chunk_id}]->(b:Entity)
//   (a:Entity)-[:CO_OCCURS_WITH {weight, evidence_chunk_ids}]->(b:Entity)
//
// Ontology (normalized predicates for REL):
//   TREATS, CAUSES, HAS_SYMPTOM, INDICATES, CONTRAINDICATED_FOR,
//   INTERACTS_WITH, SIDE_EFFECT_OF, LOCATED_IN, PART_OF

// ---------- Constraints ----------
CREATE CONSTRAINT kg_document_doc_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

CREATE CONSTRAINT kg_chunk_chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;

CREATE CONSTRAINT kg_entity_entity_id IF NOT EXISTS
FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;

// ---------- Property Indexes ----------
// Fast filters / joins
CREATE INDEX kg_chunk_doc_id IF NOT EXISTS
FOR (c:Chunk) ON (c.doc_id);

CREATE INDEX kg_entity_type IF NOT EXISTS
FOR (e:Entity) ON (e.type);

// Index for embedding model lookup
CREATE INDEX kg_chunk_embedding_model IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding_model);

// ---------- Fulltext Indexes (Neo4j 5+ syntax) ----------
// Entity search by name and aliases - enables fuzzy medical term matching
// Supports: tiểu đường = đái tháo đường = diabetes
CREATE FULLTEXT INDEX kgEntityFulltext IF NOT EXISTS
FOR (e:Entity)
ON EACH [e.canonical_name, e.aliases];

// Chunk text search for lexical fallback
CREATE FULLTEXT INDEX kgChunkFulltext IF NOT EXISTS
FOR (c:Chunk)
ON EACH [c.text, c.section_path];

// ---------- Relationship Indexes ----------
// Fast lookup by predicate type (for ontology-based traversal)
CREATE INDEX kg_rel_predicate IF NOT EXISTS
FOR ()-[r:REL]-() ON (r.predicate);

// Index for evidence tracking
CREATE INDEX kg_rel_evidence IF NOT EXISTS
FOR ()-[r:REL]-() ON (r.evidence_chunk_id);

