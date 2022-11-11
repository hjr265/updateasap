class Service:
	@classmethod
	def versions(cls):
		versions = cls.source.versions()
		for version in versions:
			yield cls.versioning.parse(version)

	@classmethod
	def latest(cls):
		return sorted(cls.versions(), reverse=True)[0]
