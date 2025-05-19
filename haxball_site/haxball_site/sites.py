from unfold.sites import UnfoldAdminSite


class NewUnfoldAdminSite(UnfoldAdminSite):
    pass

new_admin_site = NewUnfoldAdminSite(name="unfold-admin")