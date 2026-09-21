//! Identity bookkeeping only. Aimee has already selected and authorized facts.
use anyhow::{Result, ensure};
use serde_json::{Value, json};

pub fn merge(current: &[Value], incoming: &[Value]) -> Result<Vec<Value>> {
    let mut result = current.to_vec();
    for fact in incoming {
        let r = &fact["memory_ref"];
        ensure!(
            ["namespace", "id", "revision"]
                .iter()
                .all(|k| r[*k].as_str().is_some_and(|v| !v.is_empty())),
            "canonical memory identity required"
        );
        ensure!(fact["content"].is_string(), "fact content required");
        let key = |v: &Value| json!([v["memory_ref"]["namespace"], v["memory_ref"]["id"]]);
        if let Some(i) = result.iter().position(|old| key(old) == key(fact)) {
            result[i] = fact.clone();
        } else {
            result.push(fact.clone());
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fact(ns: &str, rev: &str, content: &str) -> Value {
        json!({"id":1,"content":content,"memory_ref":{"namespace":ns,"id":"1","revision":rev}})
    }
    #[test]
    fn same_numeric_id_across_layers_keeps_both_objects() {
        let a = fact("general", "1", "definition");
        let b = fact("server", "1", "preference");
        assert_eq!(
            merge(std::slice::from_ref(&a), std::slice::from_ref(&b)).unwrap(),
            vec![a, b]
        );
    }
    #[test]
    fn same_content_is_not_semantically_merged_by_adapter() {
        assert_eq!(
            merge(
                &[],
                &[fact("general", "1", "same"), fact("server", "1", "same")]
            )
            .unwrap()
            .len(),
            2
        );
    }
    #[test]
    fn new_revision_replaces_only_same_source_object() {
        let old = vec![fact("general", "1", "base"), fact("server", "1", "old")];
        let new = merge(&old, &[fact("server", "2", "new")]).unwrap();
        assert_eq!(new, vec![old[0].clone(), fact("server", "2", "new")]);
        assert_eq!(old[1]["content"], "old");
    }
    #[test]
    fn unqualified_fact_is_rejected() {
        assert!(merge(&[], &[json!({"id":1,"content":"unbound"})]).is_err());
    }
}
