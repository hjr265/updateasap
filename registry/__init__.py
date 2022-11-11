from .gitlabfoss import GitLabFoss
from .go import Go
from .portainer import Portainer

Services = {
	"gitlabfoss": GitLabFoss,
	"go": Go,
	"portainer": Portainer,
}
