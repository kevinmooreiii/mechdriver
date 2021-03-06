"""
Executes the automation part of 1DMin
"""

import statistics
import autofile
from routines.trans._routines import _geom as geom
from routines.trans._routines import _gather as gather
from routines.trans.runner import lj as lj_runner
from lib import submission
from lib import filesys
from lib import amech_io


def onedmin(spc_name,
            spc_dct, thy_dct, etrans_keyword_dct,
            run_prefix, save_prefix):
    """ Run the task
    """

    bath_name = etrans_keyword_dct['bath']

    tgt_dct, bath_dct = spc_dct[spc_name], spc_dct[bath_name]
    tgt_info = filesys.inf.get_spc_info(tgt_dct)
    bath_info = filesys.inf.get_spc_info(bath_dct)
    lj_info = filesys.inf.combine_spc_info(tgt_info, bath_info)

    # Build the modified thy objs
    inp_thy_info = filesys.inf.get_es_info(
        etrans_keyword_dct['inplvl'], thy_dct)
    run_thy_info = filesys.inf.get_es_info(
        etrans_keyword_dct['runlvl'], thy_dct)
    tgt_mod_thy_info = filesys.inf.modify_orb_restrict(
        tgt_info, inp_thy_info)
    bath_mod_thy_info = filesys.inf.modify_orb_restrict(
        bath_info, inp_thy_info)
    lj_mod_thy_info = filesys.inf.modify_orb_restrict(
        lj_info, run_thy_info)

    # Build the target conformer filesystem objects
    _, tgt_thy_run_path = filesys.build.spc_thy_fs_from_root(
        run_prefix, tgt_info, tgt_mod_thy_info)
    _, tgt_thy_save_path = filesys.build.spc_thy_fs_from_root(
        save_prefix, tgt_info, tgt_mod_thy_info)

    tgt_cnf_run_fs = autofile.fs.conformer(tgt_thy_run_path)
    tgt_cnf_save_fs = autofile.fs.conformer(tgt_thy_save_path)

    tgt_loc_info = filesys.mincnf.min_energy_conformer_locators(
        tgt_cnf_save_fs, tgt_mod_thy_info)
    tgt_min_cnf_locs, tgt_cnf_save_path = tgt_loc_info
    tgt_cnf_run_fs[-1].create(tgt_min_cnf_locs)
    tgt_cnf_run_path = filesys.build.cnf_paths_from_locs(
        tgt_cnf_run_fs, [tgt_min_cnf_locs])[0]

    # Build the target energy transfer filesystem objects
    etrans_run_fs, _ = filesys.build.etrans_fs_from_prefix(
        tgt_cnf_run_path, bath_info, lj_mod_thy_info)
    etrans_save_fs, etrans_locs = filesys.build.etrans_fs_from_prefix(
        tgt_cnf_save_path, bath_info, lj_mod_thy_info)

    # Build the bath conformer filesystem objects
    _, bath_thy_save_path = filesys.build.spc_thy_fs_from_root(
        save_prefix, bath_info, bath_mod_thy_info)
    print('bath path', bath_thy_save_path)
    bath_cnf_save_fs = autofile.fs.conformer(bath_thy_save_path)

    # Calculate and save the Lennard-Jones parameters, if needed
    run_needed, nsamp_needed = _need_run(
        etrans_save_fs, etrans_locs, etrans_keyword_dct)
    if run_needed:
        _runlj(nsamp_needed,
               lj_info, lj_mod_thy_info,
               tgt_mod_thy_info, bath_mod_thy_info,
               tgt_cnf_save_fs, bath_cnf_save_fs,
               etrans_run_fs, etrans_locs,
               etrans_keyword_dct)
        _savelj(etrans_run_fs, etrans_save_fs, etrans_locs,
                etrans_keyword_dct)
    else:
        epath = etrans_save_fs[-1].file.lennard_jones_epsilon.path(etrans_locs)
        spath = etrans_save_fs[-1].file.lennard_jones_sigma.path(etrans_locs)
        print('- Lennard-Jones epsilon found at path {}'.format(epath))
        print('- Lennard-Jones sigma found at path {}'.format(spath))


def _need_run(etrans_save_fs, etrans_locs, etrans_keyword_dct):
    """ Check if job needs to run
    """

    nsamp = etrans_keyword_dct['nsamp']
    overwrite = etrans_keyword_dct['overwrite']

    ex1 = etrans_save_fs[-1].file.lennard_jones_epsilon.exists(etrans_locs)
    ex2 = etrans_save_fs[-1].file.lennard_jones_sigma.exists(etrans_locs)
    if not ex1 or not ex2:
        print('Either no Lennard-Jones epsilon or sigma found in'
              'in save filesys. Running OneDMin for params...')
        run = True
        nsamp_need = nsamp
    elif overwrite:
        print('User specified to overwrite parameters with new run...')
        run = True
        nsamp_need = nsamp
    else:
        inf_obj = etrans_save_fs[-1].file.info.read(etrans_locs)
        nsampd = inf_obj.nsamp
        if nsamp < nsampd:
            run = True
            nsamp_need = nsampd - nsamp
        else:
            run = False
            nsamp_need = 0

    return run, nsamp_need


def _runlj(nsamp_needed,
           lj_info, lj_mod_thy_info,
           tgt_mod_thy_info, bath_mod_thy_info,
           tgt_cnf_save_fs, bath_cnf_save_fs,
           etrans_run_fs, etrans_locs,
           etrans_keyword_dct):
    """ Run the Lennard-Jones parameters
    """

    # Pull stuff from dct
    njobs = etrans_keyword_dct['njobs']
    smin = etrans_keyword_dct['smin']
    smax = etrans_keyword_dct['smax']
    conf = etrans_keyword_dct['conf']

    # Determine the number of samples per job
    nsamp_per_job = nsamp_needed // njobs

    # Set the path to the executable
    onedmin_exe_path = '/lcrc/project/CMRP/amech/OneDMin/build'

    # Obtain the geometry for the target and bath
    tgt_geo = geom.get_geometry(
        tgt_cnf_save_fs, tgt_mod_thy_info, conf=conf)
    bath_geo = geom.get_geometry(
        bath_cnf_save_fs, bath_mod_thy_info, conf=conf)

    # Set the path to the etrans lead fs
    etrans_run_path = etrans_run_fs[-1].path(etrans_locs)

    # Build the run directory
    onedmin_run_path = lj_runner.build_rundir(etrans_run_path)

    # Run an instancw of 1DMin for each processor
    for idx in range(njobs):

        # Build run directory
        onedmin_job_path = lj_runner.make_jobdir(onedmin_run_path, idx)

        # Write the input files
        xyz1_str, xyz2_str = lj_runner.write_xyz(tgt_geo, bath_geo)

        elstruct_inp_str, elstruct_sub_str = lj_runner.write_elstruct_inp(
            lj_info, lj_mod_thy_info)

        onedmin_str = lj_runner.write_input(
            nsamp_per_job, smin=smin, smax=smax,
            target_name='target.xyz', bath_name='bath.xyz')

        input_strs = (
            xyz1_str, xyz2_str,
            elstruct_inp_str, elstruct_sub_str,
            onedmin_str)
        input_names = (
            'target.xyz', 'bath.xyz',
            'qc.mol', 'ene.x',
            'input.dat')
        inp = tuple(zip(input_strs, input_names))
        amech_io.writer.write_files(
            inp, onedmin_job_path, exe_names=('ene.x'))

    # Write the batch submission script for each instance
    onedmin_sub_str = lj_runner.write_onedmin_sub(
        njobs, onedmin_run_path, onedmin_exe_path,
        exe_name='onedmin-dd-molpro.x')
    sub_inp = ((onedmin_sub_str, 'build.sh'),)
    amech_io.writer.write_files(
        sub_inp, onedmin_run_path, exe_names=('build.sh'))

    # Submit the all of the OneDMin jobs
    print('\n\nRunning each OneDMin job...')
    submission.run_script(onedmin_sub_str, onedmin_run_path)


def _savelj(etrans_run_fs, etrans_save_fs, etrans_locs,
            etrans_keyword_dct):
    """ Save the Lennard-Jones parameters
    """

    # Read the dictionary
    ljpotential = etrans_keyword_dct['pot']

    # Set the run path to read the files
    etrans_run_path = etrans_run_fs[-1].path(etrans_locs)

    # Read any epsilons and sigma currently in the filesystem
    print('\nReading Lennard-Jones parameters and Geoms from filesystem...')
    fs_geoms, fs_epsilons, fs_sigmas = gather.read_filesys(
        etrans_save_fs, etrans_locs)
    gather.print_lj_parms(fs_sigmas, fs_epsilons)

    # Read the lj from all the output files
    print('\nReading Lennard-Jones parameters and Geoms from output...')
    run_geoms, run_epsilons, run_sigmas = gather.read_output(etrans_run_path)
    gather.print_lj_parms(run_sigmas, run_epsilons)

    # Read the program and version for onedmin
    prog_version = gather.prog_version(etrans_run_path)

    # Add the lists from the two together
    geoms = fs_geoms + run_geoms
    sigmas = fs_sigmas + run_sigmas
    epsilons = fs_epsilons + run_epsilons

    # Average the sigma and epsilon values
    if geoms and sigmas and epsilons:

        assert len(geoms) == len(sigmas) == len(epsilons), (
            'Number of geoms, sigmas, and epsilons not the same'
        )

        avg_sigma = statistics.mean(sigmas)
        avg_epsilon = statistics.mean(epsilons)
        nsampd = len(sigmas)
        print('\nAverage Sigma to save [unit]:', avg_sigma)
        print('Average Epsilont to save [unit]:', avg_epsilon)
        print('Number of values = ', nsampd)

        # Update the trajectory file
        traj = []
        for geo, eps, sig in zip(geoms, epsilons, sigmas):
            comment = 'Epsilon: {}   Sigma: {}'.format(eps, sig)
            traj.append((comment, geo))

        # Write the info obj
        inf_obj = autofile.schema.info_objects.lennard_jones(
            nsampd, potential=ljpotential,
            program='OneDMin', version=prog_version)

        # Set up the electronic structure input file
        onedmin_inp_str = '<ONEDMIN INP>'
        els_inp_str = '<ELSTRUCT INP>'

        # Write the params to the save file system
        etrans_save_fs[-1].file.lj_input.write(onedmin_inp_str, etrans_locs)
        etrans_save_fs[-1].file.info.write(inf_obj, etrans_locs)
        etrans_save_fs[-1].file.molpro_inp_file.write(els_inp_str, etrans_locs)
        etrans_save_fs[-1].file.epsilon.write(avg_epsilon, etrans_locs)
        etrans_save_fs[-1].file.sigma.write(avg_sigma, etrans_locs)
        etrans_save_fs[1].file.trajectory.write(traj, etrans_locs)
