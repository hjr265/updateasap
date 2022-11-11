from semver import VersionInfo
import semver

class Semver:
	def __init__(self, strip_v=False, extract=None):
		self.extract = extract
		self.strip_v = strip_v

	def parse(self, string):
		if self.strip_v:
			string = string.lstrip('v')
		if self.extract:
			string = self.extract(string)
		return VersionInfo.parse(string)

	def compare(self, version, other):
		return semver.compare(version, other)
