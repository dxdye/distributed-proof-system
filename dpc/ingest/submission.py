"""Submission record (interface I-1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dpc.lean.project import COMMIT_RE


class Submission(BaseModel):
    """What a submitter hands in: repository, pinned commit, main theorem, paper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_url: str = Field(min_length=1)
    commit: str = Field(pattern=COMMIT_RE.pattern, description="full 40-character commit hash")
    root: str = Field(min_length=1, description="fully qualified name of the main theorem T")
    root_module: str = Field(min_length=1, description="module that declares T")
    project_dir: str = Field(
        default="",
        pattern=r"^(?:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)?$",
        description="sub-directory of the repository that contains the Lake project",
    )
    patch_dir: str | None = Field(
        default=None,
        description="directory (relative to the project) with dependency patches "
                    "`<package>-*.patch`, applied with git before the build",
    )
    paper_ref: str | None = None

    @field_validator("project_dir")
    @classmethod
    def _no_parent(cls, value: str) -> str:
        if ".." in value.split("/"):
            raise ValueError("project_dir must stay inside the repository")
        return value

    @field_validator("patch_dir")
    @classmethod
    def _patch_dir_inside(cls, value: str | None) -> str | None:
        if value is not None and (".." in value.split("/") or value.startswith("/")):
            raise ValueError("patch_dir must stay inside the project")
        return value
