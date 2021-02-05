""" Handle symmetry factor stuff
"""

import automol
from autofile import fs
from mechlib import structure
from mechlib.amech_io import printer as ioprinter


def symmetry_factor(pf_filesystems, pf_models, spc_dct_i, rotors,
                    grxn=None):
    """ Calculate the symmetry factor for a species
        Note: ignoring for saddle pts the possibility that two configurations
        differ only in their torsional values.
        As a result, the symmetry factor is a lower bound of the true value
    """

    if 'sym_factor' in spc_dct_i:
        sym_factor = spc_dct_i['sym_factor']
        ioprinter.info_message(' - Reading symmetry number input by user:', sym_factor)
    else:

        zrxn = spc_dct_i.get('zrxn', None)
        if zrxn is not None:
            grxn = automol.reac.relabel_for_geometry(zrxn)
        else:
            grxn = None

        # if automol.geom.is_atom(geo):
        sym_model = pf_models['sym']

        # Obtain geometry, energy, and symmetry filesystem
        [cnf_fs, cnf_path, min_cnf_locs, _, _] = pf_filesystems['sym']
        geo = cnf_fs[-1].file.geometry.read(min_cnf_locs)

        # Obtain the external symssetry number
        ext_sym = automol.geom.external_symmetry_factor(geo)

        # Obtain the internal symmetry number using some routine
        if sym_model == 'sampling':

            # Set up the symmetry filesystem
            sym_fs = fs.symmetry(cnf_path)
            sym_geos = [geo]
            sym_geos += [sym_fs[-1].file.geometry.read(locs)
                         for locs in sym_fs[-1].existing()]

            # Obtain the internal
            if rotors:
                ioprinter.info_message(
                    ' - Determining internal sym number ',
                    'using sampling routine.')
                int_sym = int_sym_num_from_sampling(sym_geos, grxn=grxn)
            else:
                ioprinter.info_message(' - No torsions, internal sym is 1.0')
                int_sym = 1.0

        else:
            ioprinter.info_message(
                'No symmetry model requested, ',
                'setting internal sym factor to 1.0')
            int_sym = 1.0

        # Obtain overall number
        sym_factor = ext_sym * int_sym

        # Reduce sym factor using rotor symmetries
        sym_factor = tors_reduced_sym_factor(sym_factor, rotors)

        # ioprinter.info_message('sym_factor test:', sym_factor)

    return sym_factor


def int_sym_num_from_sampling(sym_geos, grxn=None):
    """ Determine the symmetry number for a given conformer geometry.
    (1) Explore the saved conformers to find the list of similar conformers -
        i.e. those with a coulomb matrix and energy that are equivalent
        to those for the reference geometry.
    (2) Expand each of those similar conformers by applying
        rotational permutations to each of the terminal groups.
    (3) Count how many distinct distance matrices there are in
        the fully expanded conformer list.
    """

    if grxn is None:
        frm_bnd_keys = automol.reac.forming_bond_keys(grxn)
        brk_bnd_keys = automol.reac.breaking_bond_keys(grxn)
    else:
        frm_bnd_keys, brk_bnd_keys = frozenset({}), frozenset({})

    int_sym_num = 0
    # modify geometries to remove H's from rotatable XHn end group
    # this will be accounted for separately as multiplicative factor
    mod_sym_geos = []
    for geo_sym_i in sym_geos:
        ret = automol.geom.end_group_symmetry_factor(
            geo_sym_i, frm_bnd_keys, brk_bnd_keys)
        mod_geo_sym_i, end_group_factor = ret
        # ioprinter.info_message('end_group_factor test:', end_group_factor)

        new_geom = True
        for mod_geo_sym_j in mod_sym_geos:
            if automol.geom.almost_equal_dist_matrix(
                    mod_geo_sym_i, mod_geo_sym_j, thresh=3e-1):
                if grxn is not None:
                    new_geom = False
                    break
                tors_same = structure.geom.are_torsions_same(
                    mod_geo_sym_i, mod_geo_sym_j, ts_bnds=())
                if tors_same:
                    new_geom = False
                    break
        if new_geom:
            mod_sym_geos.append(mod_geo_sym_i)
            int_sym_num += 1

    int_sym_num *= end_group_factor

    return int_sym_num


def tors_reduced_sym_factor(sym_factor, rotors):
    """ Decrease the overall molecular symmetry factor by the
        torsional mode symmetry numbers
    """
    tors_symms = automol.rotors.symmetries(rotors, flat=True)
    for symm in tors_symms:
        sym_factor /= tors_dct['sym_num']

    return sym_factor
