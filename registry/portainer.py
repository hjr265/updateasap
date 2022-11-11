import re

from core.atom import Atom
from core.semver import Semver

from .service import Service

class Portainer(Service):
	name = 'Portainer'
	icon = ''

	source = Atom(
		'https://github.com/portainer/portainer/releases.atom',
		filters=[
			lambda e: re.match(r'Release \d+\.\d+\.\d+', e.title.value),
		],
	)

	versioning = Semver(
		extract=lambda v: re.search(r'Release (\d+\.\d+\.\d+)$', v).group(1)
	)
