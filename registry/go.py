import re

from core.atom import Atom
from core.semver import Semver

from .service import Service

class Go(Service):
	name = 'Go'
	icon = 'go.png'

	source = Atom(
		'https://github.com/golang/go/tags.atom',
		filters=[
			lambda e: re.match(r'(\[.+?\] )?go\d+\.\d+\.\d+', e.title.value),
		],
	)

	versioning = Semver(
		extract=lambda v: re.search(r'go(\d+\.\d+\.\d+)$', v).group(1)
	)
