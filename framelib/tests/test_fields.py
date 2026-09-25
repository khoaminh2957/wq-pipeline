from framelib import fields as FL


def test_presence_comes_from_the_catalogue_and_skips_symbol_and_reserved(fl):
    usa = fl.ids_in("USA/d1")
    assert "grp_x" in usa and "f_unlabelled" in usa
    assert "sym_x" not in usa and "industry" not in usa
    assert fl.excluded == {"SYMBOL": 1, "reserved name": 1}
    assert sorted(fl.ids_in("EUR/d1")) == ["f_level_a", "f_region"]
    assert fl.cells() == ["EUR/d1", "USA/d1"]


def test_signature_reads_the_structure_of_the_cell(fl):
    assert fl.signature("f_region", "USA/d1")[0] == "MATRIX"
    assert fl.signature("f_region", "EUR/d1")[0] == "VECTOR"
    assert fl.signature("grp_x", "USA/d1") == FL.UNLABELLED
    assert fl.signature("f_unlabelled", "USA/d1") == FL.UNLABELLED
    assert fl.signature("f_vec", "USA/d1")[4] == ("vec_avg", "vec_max", "vec_min")


def test_record_carries_the_typed_metadata(fl):
    r = fl.record("f_sparse", "USA/d1")
    assert (r["dataset"], r["kind"], r["unit"], r["sparsity"], r["structure"]) == ("dsA", "level", "currency", "sparse", "MATRIX")
    assert (r["crowding"], r["users"], r["sign"], r["universes"]) == ("light", 3, "+", ["TOP3000"])
    assert r["catalogue_users"] == 5 and r["labelled"] is True
    g = fl.record("grp_x", "USA/d1")
    assert (g["labelled"], g["kind"], g["structure"]) == (False, "group", "GROUP")
    assert fl.record("f_count", "EUR/d1") is None


def test_index_groups_by_signature_then_dataset(fl):
    idx = fl.index("USA/d1")
    lvl = fl.signature("f_level_a", "USA/d1")
    assert idx[lvl] == {"dsA": ["f_level_a"], "dsB": ["f_level_b"], "dsC": ["f_level_c"], "dsE": ["f_region"]}


def test_cells_filter_reads_only_those_catalogues(meta_dir):
    lib = FL.FieldLibrary.build(meta_dir / "field_labels.jsonl", meta_dir / "fields", cells=["EUR/d1"])
    assert lib.cells() == ["EUR/d1"]
