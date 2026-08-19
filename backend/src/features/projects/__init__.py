"""Projects: the unit of access control, and the level everything else sits at.

Creating a project is how a user carves out a space that is theirs, and
granting membership is how they let somebody else in. Membership is the whole
of the answer to who may do what at the project level, which is why nothing
here has an owner column and why every other feature under `src.features`
resolves a project before it decides anything.
"""
