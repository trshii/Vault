from vault_controller import VaultController
from db_model import FinanceModel
from vault_view_tmnl import VaultTmnlView

if __name__ == "__main__":
    db_name = "finance.db"
    model = FinanceModel(db_name)
    view = VaultTmnlView()
    cont = VaultController(model, view)
    
    if not cont.has_first_init:
        cont.init_run()
    else:
        cont.run()