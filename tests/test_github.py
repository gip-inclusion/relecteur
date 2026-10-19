from relecteur.github import SUMMARY_MARKER, lines_in_patch, placed, summary_body
from relecteur.review import Finding

PATCH = """@@ -10,3 +10,4 @@ class User
   validates :email
-  validates :name
+  validates :name, presence: true
+  validates :phone_number
 end
@@ -40,2 +41,3 @@ def archived?
   archived_at.present?
+  # archived
 end"""
DIFF_LINES = {"app/models/user.rb": lines_in_patch(PATCH)}


def finding(start, end=None, path="app/models/user.rb"):
    return Finding(path, start, end or start, "Le numéro n'est pas validé.")


def test_a_comment_may_target_the_added_and_context_lines_of_the_new_file():
    assert lines_in_patch(PATCH) == {10, 11, 12, 13, 41, 42, 43}


def test_a_finding_on_lines_of_the_diff_is_commented_on_them():
    assert placed([finding(11, 12)], DIFF_LINES, {}) == ([finding(11, 12)], [])


def test_a_finding_on_lines_the_diff_leaves_out_goes_in_the_summary():
    findings = [finding(20), finding(13, 41), finding(1, path="app/models/rdv.rb")]

    assert placed(findings, DIFF_LINES, {}) == ([], findings)


def test_a_finding_on_lines_already_commented_is_not_posted_again():
    assert placed([finding(11, 12)], DIFF_LINES, {"app/models/user.rb": [range(12, 14)]}) == (
        [],
        [],
    )


def test_the_summary_lists_the_findings_it_could_not_post_on_their_lines():
    assert summary_body("✅ **relecteur** a relu cette PR.", [finding(20), finding(1, 3)]) == (
        f"{SUMMARY_MARKER}\n✅ **relecteur** a relu cette PR.\n\n"
        "Remarques sur des lignes que cette PR ne modifie pas :\n\n"
        "**`app/models/user.rb`, ligne 20**\n\nLe numéro n'est pas validé.\n\n"
        "**`app/models/user.rb`, lignes 1 à 3**\n\nLe numéro n'est pas validé."
    )
