""" drivers for coordinate scans
"""

import itertools
import automol
import autorun
import autofile
from autofile import fs
from phydat import phycon


def read_hr_pot(names, grid_vals, cnf_save_path,
                mod_tors_ene_info, ref_ene,
                constraint_dct,
                read_geom=False, read_grad=False,
                read_hess=False, read_zma=False):
    """ Get the potential for a hindered rotor
    """

    # Build initial lists for storing potential energies and Hessians
    grid_points = automol.pot.points(grid_vals)
    grid_coords = automol.pot.coords(grid_vals)
    pot, geoms, grads, hessians, zmas, paths = {}, {}, {}, {}, {}, {}

    # Set up filesystem information
    zma_fs = fs.zmatrix(cnf_save_path)
    zma_path = zma_fs[-1].path([0])
    if constraint_dct is None:
        scn_fs = autofile.fs.scan(zma_path)
    else:
        scn_fs = autofile.fs.cscan(zma_path)

    # Read the energies and Hessians from the filesystem
    for point, vals in zip(grid_points, grid_coords):

        locs = [names, vals]
        if constraint_dct is not None:
            locs = [constraint_dct] + locs

        ene = read_tors_ene(scn_fs, locs, mod_tors_ene_info)
        if ene is not None:
            pot[point] = (ene - ref_ene) * phycon.EH2KCAL
        else:
            pot[point] = -10.0

        if read_geom:
            if scn_fs[-1].file.geometry.exists(locs):
                geoms[point] = scn_fs[-1].file.geometry.read(locs)
            else:
                geoms[point] = None

        if read_grad:
            if scn_fs[-1].file.gradient.exists(locs):
                grads[point] = scn_fs[-1].file.gradient.read(locs)
            else:
                grads[point] = None

        if read_hess:
            if scn_fs[-1].file.hessian.exists(locs):
                hessians[point] = scn_fs[-1].file.hessian.read(locs)
            else:
                hessians[point] = None

        if read_zma:
            if scn_fs[-1].file.zmatrix.exists(locs):
                zmas[point] = scn_fs[-1].file.zmatrix.read(locs)
            else:
                zmas[point] = None

        paths[point] = scn_fs[-1].path(locs)

    return pot, geoms, grads, hessians, zmas, paths


def calc_hr_frequencies(geoms, grads, hessians, run_path):
    """ Calculate the frequencies
    """

    # Initialize hr freqs list
    hr_freqs = {}
    for point in geoms.keys():
        _, proj_freqs, _, _ = autorun.projrot.frequencies(
            autorun.SCRIPT_DCT['projrot'],
            run_path,
            [geoms[point]],
            [grads[point]],
            [hessians[point]])
        hr_freqs[point] = proj_freqs

    return hr_freqs


def read_tors_ene(filesys, locs, mod_tors_ene_info):
    """ read the energy for torsions
    """

    if filesys[-1].exists(locs):
        path = filesys[-1].path(locs)
        sp_fs = autofile.fs.single_point(path)
        if sp_fs[-1].file.energy.exists(mod_tors_ene_info[1:4]):
            ene = sp_fs[-1].file.energy.read(mod_tors_ene_info[1:4])
        else:
            ene = None
    else:
        ene = None

    return ene


def print_hr_pot(tors_pots):
    """ Check hr pot to see if a new mimnimum is needed
    """

    print('\nHR potentials...')
    for name in tors_pots:

        print('- Rotor {}'.format(name))
        pot_str = ''
        for pot in tors_pots[name].values():
            pot_str += ' {0:.2f}'.format(pot)

        print('- Pot:{}'.format(pot_str))