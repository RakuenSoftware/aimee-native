//! Private owned-store format shared by preparation and runtime readers.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Segment {
    pub layer: usize,
    pub value: bool,
    pub heads: usize,
    pub width: usize,
    #[serde(default)]
    pub positions: Option<usize>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Schema {
    pub segments: Vec<Segment>,
    pub row_bytes: usize,
}
#[derive(Clone, Serialize, Deserialize)]
pub(crate) struct Record {
    pub(crate) offset: u64,
    pub(crate) tokens: Vec<u32>,
}
#[derive(Serialize, Deserialize)]
pub(crate) struct Index {
    pub(crate) version: u32,
    pub(crate) model: String,
    pub(crate) schema: Schema,
    pub(crate) prototypes: usize,
    pub(crate) dictionary_bytes: usize,
    pub(crate) dictionary_sha256: String,
    pub(crate) records: BTreeMap<String, Record>,
    pub(crate) experimental_approximation: bool,
    #[serde(default)]
    pub(crate) head_major: bool,
    #[serde(default)]
    pub(crate) native_layout: bool,
}
