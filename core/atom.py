import re
import functools

import atoma
import requests

class Atom:
	def __init__(self, url, filters=[]):
		self.url = url
		self.filters = filters

	def versions(self):
		resp = requests.get(self.url)
		feed = atoma.parse_atom_bytes(resp.content)
		entries = self._filtered(feed.entries)
		for entry in entries:
			yield entry.title.value

	def _filtered(self, entries):
		for entry in entries:
			match = True
			for rule in self.filters:
				if not rule(entry):
					match = False
			if match:
				yield entry
