import re

from core.atom import Atom
from core.semver import Semver

from .service import Service

class GitLabFoss(Service):
	name = 'GitLab FOSS'
	icon = 'gitlab.png'

	source = Atom(
		'https://gitlab.com/gitlab-org/gitlab-foss/-/tags?format=atom',
		filters=[
			lambda e: re.match(r'v\d+\.\d+\.\d+', e.title.value),
		],
	)

	versioning = Semver(
		strip_v=True
	)
