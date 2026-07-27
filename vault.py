from vault_controller import VaultController
from db_model import FinanceModel
from vault_view_tmnl import VaultTmnlView

if __name__ == "__main__":
    view = VaultTmnlView()
    db_name = view.get_db_file_name()
    model = FinanceModel(db_name)
    cont = VaultController(model, view)
    
    if not cont.has_first_init:
        cont.init_run()
    else:
        cont.run()