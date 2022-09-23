# Licensed under a 3-clause BSD style license - see LICENSE
'''
This module provides the framework to handle the creation of the perturbation
component of the astrometric uncertainty function.
'''

import os
import sys
import numpy as np

from .misc_functions import (create_auf_params_grid, _load_single_sky_slice,
                             _load_rectangular_slice, _create_rectangular_slice_arrays)
from .misc_functions_fortran import misc_functions_fortran as mff
from .get_trilegal_wrapper import get_trilegal
from .perturbation_auf_fortran import perturbation_auf_fortran as paf
from .galaxy_counts import create_galaxy_counts

__all__ = ['make_perturb_aufs', 'create_single_perturb_auf']


def make_perturb_aufs(auf_folder, cat_folder, filters, auf_points, r, dr, rho,
                      drho, which_cat, include_perturb_auf, mem_chunk_num, use_memmap_files,
                      tri_download_flag=False, delta_mag_cuts=None, psf_fwhms=None,
                      tri_set_name=None, tri_filt_num=None, tri_filt_names=None,
                      tri_maglim_bright=None, tri_maglim_faint=None, tri_num_bright=None,
                      tri_num_faint=None, auf_region_frame=None, num_trials=None, j0s=None,
                      density_mags=None, d_mag=None, compute_local_density=None,
                      density_radius=None, run_fw=None, run_psf=None, dd_params=None, l_cut=None,
                      mag_h_params=None, fit_gal_flag=None, cmau_array=None, wavs=None, z_maxs=None,
                      nzs=None, ab_offsets=None, filter_names=None, al_avs=None, alpha0=None,
                      alpha1=None, alpha_weight=None):
    r"""
    Function to perform the creation of the blended object perturbation component
    of the AUF.

    Parameters
    ----------
    auf_folder : string
        The overall folder into which to create filter-pointing folders and save
        individual simulation files.
    cat_folder : string
        The folder that the photometric catalogue being simulated for perturbation
        AUF component is stored in.
    filters : list of strings or numpy.ndarray of strings
        An array containing the list of filters in this catalogue to create
        simulated AUF components for.
    auf_points : numpy.ndarray
        Two-dimensional array containing pairs of coordinates at which to evaluate
        the perturbation AUF components.
    r : numpy.ndarray
        The real-space coordinates for the Hankel transformations used in AUF-AUF
        convolution.
    dr : numpy.ndarray
        The spacings between ``r`` elements.
    rho : numpy.ndarray
        The fourier-space coordinates for Hankel transformations.
    drho : numpy.ndarray
        The spacings between ``rho`` elements.
    which_cat : string
        Indicator as to whether these perturbation AUFs are for catalogue "a"
        or catalogue "b" within the cross-match process.
    include_perturb_auf : boolean
        ``True`` or ``False`` flag indicating whether perturbation component of the
        AUF should be used or not within the cross-match process.
    mem_chunk_num : int
        Number of individual sub-sections to break catalogue into for memory
        saving purposes.
    use_memmap_files : boolean
        When set to True, memory mapped files are used for several internal
        arrays. Reduces memory consumption at the cost of increased I/O
        contention.
    tri_download_flag : boolean, optional
        A ``True``/``False`` flag, whether to re-download TRILEGAL simulated star
        counts or not if a simulation already exists in a given folder. Only
        needed if ``include_perturb_auf`` is True.
    delta_mag_cuts : numpy.ndarray, optional
        Array of magnitude offsets corresponding to relative fluxes of perturbing
        sources, for consideration of relative contamination chances. Must be given
        if ``include_perturb_auf`` is ``True``.
    psf_fwhms : numpy.ndarray, optional
        Array of full width at half-maximums for each filter in ``filters``. Only
        required if ``include_perturb_auf`` is True; defaults to ``None``.
    tri_set_name : string, optional
        Name of the filter set to generate simulated TRILEGAL Galactic source
        counts from. If ``include_perturb_auf`` and ``tri_download_flag`` are
        ``True``, this must be set.
    tri_filt_num : string, optional
        Column number of the filter defining the magnitude limit of simulated
        TRILEGAL Galactic sources. If ``include_perturb_auf`` and
        ``tri_download_flag`` are ``True``, this must be set.
    tri_filt_names : list or array of strings, optional
        List of filter names in the TRILEGAL filterset defined in ``tri_set_name``,
        in the same order as provided in ``psf_fwhms``. If ``include_perturb_auf``
        and ``tri_download_flag`` are ``True``, this must be set.
    tri_maglim_bright : float
        Magnitude in the primary ``tri_filt_num`` filter to simulate sources to
        in the smaller "bright" simulation, used to ensure accurate statistics
        at the bright end of the dynamic survey range. If ``include_perturb_auf``
        and ``tri_download_flag`` are ``True``, this must be set.
    tri_maglim_faint : float
        Magnitude in the primary TRILEGAL filter to simulate sources down to for
        the main, "faint" simulation, used to capture the differential source
        counts at all appropriate magnitudes. If ``include_perturb_auf`` and        ``tri_download_flag`` are ``True``, this must be set.
    tri_num_bright : integer
        Number of objects to simulate in the bright TRILEGAL simulation. Should
        be large enough to capture robust number statistics at bright, low
        source count brightnesses, but low enough to be realistic in runtime.
        If ``include_perturb_auf`` and ``tri_download_flag`` are ``True``, this
        must be set.
    tri_num_faint : integer
        Number of objects to simulate in the main TRILEGAL simulation. Should
        capture sufficient numbers to be accurate without overrunning simulation
        times. If ``include_perturb_auf`` and ``tri_download_flag`` are ``True``,
        this must be set.
    auf_region_frame : string, optional
        Coordinate reference frame in which sky coordinates are defined, either
        ``equatorial`` or ``galactic``, used to define the coordinates TRILEGAL
        simulations are generated in. If ``include_perturb_auf`` and
        ``tri_download_flag`` are ``True``, this must be set.
    num_trials : integer, optional
        The number of simulated PSFs to compute in the derivation of the
        perturbation component of the AUF. Must be given if ``include_perturb_auf``
        is ``True``.
    j0s : numpy.ndarray, optional
        The Bessel Function of First Kind of Zeroth Order evaluated at each
        ``r``-``rho`` combination. Must be given if ``include_perturb_auf``
        is ``True``.
    density_mags : numpy.ndarray, optional
        The faintest magnitude down to which to consider number densities of
        objects for normalisation purposes, in each filter, in the same order
        as ``psf_fwhms``. Must be given if ``include_perturb_auf`` is ``True``.
        Must be the same as were used to calculate ``count_density`` in
        ``calculate_local_density``, if ``compute_local_density`` is ``False``
        and pre-computed densities are being used.
    d_mag : float, optional
        The resolution at which to create the TRILEGAL source density distribution.
        Must be provided if ``include_perturb_auf`` is ``True``.
    compute_local_density : boolean, optional
        Flag to indicate whether to calculate local source densities during
        the cross-match process, or whether to use pre-calculated values. Must
        be provided if ``include_perturb_auf`` is ``True``.
    density_radius : float, optional
        The astrometric distance, in degrees, within which to consider numbers
        of internal catalogue sources, from which to calculate local density.
        Must be given if both ``include_perturb_auf`` and
        ``compute_local_density`` are both ``True``.
    run_fw : bool, optional
        Flag indicating whether to run the "flux-weighted" version of the
        perturbation algorithm. Must be given if ``include_perturb_auf`` is
        ``True``.
    run_psf : bool, optional
        Flag indicating whether to run the "background-dominated PSF" version
        of the perturbation algorithm. Must be given if ``include_perturb_auf``
        is ``True``.
    dd_params : numpy.ndarray, optional
        Polynomial fits for the various parameters controlling the background
        limited PSF-fit algorithm for centroid perturbations. Must be given if
        ``include_perturb_auf`` is ``True`` and ``run_psf`` is ``True``.
    l_cut : numpy.ndarray or list, optional
        Relative flux cutoffs for which algorithm to use in the background
        limited PSF-fit algorithm case. Must be given if ``include_perturb_auf``
        is ``True`` and ``run_psf`` is ``True``.
    mag_h_params : numpy.ndarray, optional
        Array, of shape ``(N, 5)``, containing the pre-determined values of the
        magnitude-perturbation weighting relationship for a series of Galactic
        sightlines. Must be given if ``include_perturb_auf`` is ``True``.
    fit_gal_flag : boolean, optional
        Flag indicating whether to include galaxy counts in derivations of
        perturbation component of the AUF. Must be given if
        ``include_perturb_auf`` is ``True``.
    cmau_array : numpy.ndarray, optional
        Array of shape ``(5, 2, 4)`` holding the Wilson (2022, RNAAS, 6, 60) [1]_
        c, m, a, and u values that describe the Schechter parameterisation with
        wavelength.
    wavs : list of floats or numpy.ndarray, optional
        List of central wavelengths of each filter in ``filters``, used to
        compute appropriate Schechter function parameters for fitting galaxy
        counts. Must be given if ``include_perturb_auf`` and ``fit_gal_flag``
        are ``True``.
    z_maxs : list of floats or numpy.ndarray, optional
        List of maximum redshifts to compute galaxy densities out to when
        deriving Schechter functions. Must be given if ``include_perturb_auf``
        and ``fit_gal_flag`` are ``True``.
    nzs : list of integers or numpy.ndarray, optional
        Resolution of redshift grid, in the sense of ``np.linspace(0, z_max, nz)``,
        to evaluate Schechter functions on. Must be given if
        ``include_perturb_auf`` and ``fit_gal_flag`` are ``True``.
    ab_offsets : list of floats or numpy.ndarray, optional
        For filters in a non-AB magnitude system, the given offset between
        the chosen filter system and AB magnitudes, in the sense of m = m_AB -
        ab_offset. Must be given if ``include_perturb_auf`` and ``fit_gal_flag``
        are ``True``.
    filter_names : list of string, optional
        Names for each filter in ``filters`` in a ``speclite``-appropriate
        naming scheme (``group_name``-``band_name``), for loading response
        curves to calculate galaxy k-corrections. Must be given if
        ``include_perturb_auf`` and ``fit_gal_flag`` are ``True``.
    al_avs : list of numpy.ndarray or numpy.ndarray, optional
        Relative extinction curve vectors for each filter in ``filters``,
        :math:`\frac{A_\lambda}{A_V}`, to convert exinction in the V-band
        to extinction in the relevant filter. Must be given if
        ``include_perturb_auf`` and ``fit_gal_flag`` are ``True``.
    alpha0 : list of numpy.ndarray or numpy.ndarray, optional
        Indices used to calculate parameters :math:`\alpha_i`, used in deriving
        Dirichlet-distributed SED coefficients. :math:`\alpha{i, 0}` are the
        zero-redshift parameters; see [2]_ and [3]_ for more details.
    alpha1 : list of numpy.ndarray or numpy.ndarray, optional
        :math:`\alpha_{i, 1}`, indices at redshift z=1 used to derive
        Dirichlet-distributed SED coefficient values :math:`\alpha_i`.
    alpha_weight : list of numpy.ndarray or numpy.ndarray, optional
        Weights for use in calculating :math:`\alpha_i` from ``alpha0`` and
        ``alpha1``.

    References
    ----------
    .. [1] Wilson T. J. (2022), RNAAS, 6, 60
    .. [2] Herbel J., Kacprzak T., Amara A., et al. (2017), JCAP, 8, 35
    .. [3] Blanton M. R., Roweis S. (2007), AJ, 133, 734

    """
    if include_perturb_auf and tri_download_flag and tri_set_name is None:
        raise ValueError("tri_set_name must be given if include_perturb_auf and tri_download_flag "
                         "are both True.")
    if include_perturb_auf and tri_download_flag and tri_filt_num is None:
        raise ValueError("tri_filt_num must be given if include_perturb_auf and tri_download_flag "
                         "are both True.")
    if include_perturb_auf and tri_download_flag and auf_region_frame is None:
        raise ValueError("auf_region_frame must be given if include_perturb_auf and "
                         "tri_download_flag are both True.")

    if include_perturb_auf and tri_filt_names is None:
        raise ValueError("tri_filt_names must be given if include_perturb_auf is True.")
    if include_perturb_auf and delta_mag_cuts is None:
        raise ValueError("delta_mag_cuts must be given if include_perturb_auf is True.")
    if include_perturb_auf and psf_fwhms is None:
        raise ValueError("psf_fwhms must be given if include_perturb_auf is True.")
    if include_perturb_auf and num_trials is None:
        raise ValueError("num_trials must be given if include_perturb_auf is True.")
    if include_perturb_auf and j0s is None:
        raise ValueError("j0s must be given if include_perturb_auf is True.")
    if include_perturb_auf and density_mags is None:
        raise ValueError("density_mags must be given if include_perturb_auf is True.")
    if include_perturb_auf and d_mag is None:
        raise ValueError("d_mag must be given if include_perturb_auf is True.")
    if include_perturb_auf and run_fw is None:
        raise ValueError("run_fw must be given if include_perturb_auf is True.")
    if include_perturb_auf and run_psf is None:
        raise ValueError("run_psf must be given if include_perturb_auf is True.")
    if include_perturb_auf and run_psf and dd_params is None:
        raise ValueError("dd_params must be given if include_perturb_auf and run_psf are True.")
    elif include_perturb_auf and dd_params is None:
        # Fake an array to pass only to run_fw that fortran will accept:
        dd_params = np.zeros((1, 1), float)
    if include_perturb_auf and run_psf and l_cut is None:
        raise ValueError("l_cut must be given if include_perturb_auf and run_psf are True.")
    elif include_perturb_auf and l_cut is None:
        # Fake an array to pass only to run_fw that fortran will accept:
        l_cut = np.zeros((1), float)
    if include_perturb_auf and mag_h_params is None:
        raise ValueError("mag_h_params must be given if include_perturb_auf is True.")
    if include_perturb_auf and compute_local_density is None:
        raise ValueError("compute_local_density must be given if include_perturb_auf is True.")
    if include_perturb_auf and compute_local_density and density_radius is None:
        raise ValueError("density_radius must be given if include_perturb_auf and "
                         "compute_local_density are both True.")

    if include_perturb_auf and fit_gal_flag is None:
        raise ValueError("fit_gal_flag must not be None if include_perturb_auf is True.")
    if include_perturb_auf and fit_gal_flag and cmau_array is None:
        raise ValueError("cmau_array must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and wavs is None:
        raise ValueError("wavs must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and z_maxs is None:
        raise ValueError("z_maxs must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and nzs is None:
        raise ValueError("nzs must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and ab_offsets is None:
        raise ValueError("ab_offsets must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and filter_names is None:
        raise ValueError("filter_names must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and al_avs is None:
        raise ValueError("al_avs must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and alpha0 is None:
        raise ValueError("alpha0 must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and alpha1 is None:
        raise ValueError("alpha1 must be given if fit_gal_flag is True.")
    if include_perturb_auf and fit_gal_flag and alpha_weight is None:
        raise ValueError("alpha_weight must be given if fit_gal_flag is True.")

    print('Creating perturbation AUFs sky indices for catalogue "{}"...'.format(which_cat))
    sys.stdout.flush()

    n_sources = len(np.load('{}/con_cat_astro.npy'.format(cat_folder), mmap_mode='r'))

    if use_memmap_files:
        modelrefinds = np.lib.format.open_memmap('{}/modelrefinds.npy'.format(auf_folder),
                                                 mode='w+', dtype=int, shape=(3, n_sources),
                                                 fortran_order=True)
    else:
        modelrefinds = np.zeros(dtype=int, shape=(3, n_sources), order='f')

    for cnum in range(0, mem_chunk_num):
        lowind = np.floor(n_sources*cnum/mem_chunk_num).astype(int)
        highind = np.floor(n_sources*(cnum+1)/mem_chunk_num).astype(int)
        a = np.load('{}/con_cat_astro.npy'.format(cat_folder), mmap_mode='r')[lowind:highind]
        # As we chunk in even steps through the files this is simple for now,
        # but could be replaced with a more complex mapping in the future.
        indexmap = np.arange(lowind, highind, 1)

        # Which sky position to use is more complex; this involves determining
        # the smallest great-circle distance to each auf_point AUF mapping for
        # each source.
        modelrefinds[2, indexmap] = mff.find_nearest_point(a[:, 0], a[:, 1],
                                                           auf_points[:, 0], auf_points[:, 1])

    print('Creating empirical perturbation AUFs for catalogue "{}"...'.format(which_cat))
    sys.stdout.flush()

    # Store the length of the density-magnitude combinations in each sky/filter
    # combination for future loading purposes.
    if use_memmap_files:
        arraylengths = np.lib.format.open_memmap('{}/arraylengths.npy'.format(auf_folder), mode='w+',
                                                 dtype=int, shape=(len(filters), len(auf_points)),
                                                 fortran_order=True)
    else:
        arraylengths = np.zeros(dtype=int, shape=(len(filters), len(auf_points)), order='f')

    if use_memmap_files:
        # Overload compute_local_density if it is False but local_N does not exist.
        if not compute_local_density and not os.path.isfile('{}/local_N.npy'.format(auf_folder)):
            compute_local_density = True
    # Always compute_local_density if not using memmapped files
    else:
        compute_local_density = True

    if include_perturb_auf:
        a_tot_photo = np.load('{}/con_cat_photo.npy'.format(cat_folder), mmap_mode='r')
        if compute_local_density:
            a_tot_astro = np.load('{}/con_cat_astro.npy'.format(cat_folder), mmap_mode='r')
            # Set up the temporary sky slice memmap arrays quickly, as they will
            # be needed in calculate_local_density later.
            memmap_slice_arrays = []
            if use_memmap_files:
                _create_rectangular_slice_arrays(auf_folder, '', len(a_tot_astro))
                for n in ['1', '2', '3', '4', 'combined']:
                    memmap_slice_arrays.append(np.lib.format.open_memmap(
                        '{}/{}_temporary_sky_slice_{}.npy'.format(auf_folder, '', n), mode='r+',
                        dtype=bool, shape=(len(a_tot_astro),)))
            else:
                for _ in range(5):
                    memmap_slice_arrays.append(np.zeros(dtype=bool, shape=(len(a_tot_astro),)))

    if compute_local_density and include_perturb_auf:
        if use_memmap_files:
            local_N = np.lib.format.open_memmap('{}/local_N.npy'.format(auf_folder), mode='w+',
                                                dtype=float, shape=(len(a_tot_astro), len(filters)))
        else:
            local_N = np.zeros(dtype=float, shape=(len(a_tot_astro), len(filters)))

    for i in range(len(auf_points)):
        ax1, ax2 = auf_points[i]
        ax_folder = '{}/{}/{}'.format(auf_folder, ax1, ax2)
        if not os.path.exists(ax_folder):
            os.makedirs(ax_folder, exist_ok=True)

        if include_perturb_auf and (tri_download_flag or not
                                    os.path.isfile('{}/trilegal_auf_simulation_faint.dat'
                                                   .format(ax_folder))):
            download_trilegal_simulation(ax_folder, tri_set_name, ax1, ax2, tri_filt_num,
                                         auf_region_frame, tri_maglim_faint,
                                         total_objs=tri_num_faint)
            os.system('mv {}/trilegal_auf_simulation.dat {}/trilegal_auf_simulation_faint.dat'
                      .format(ax_folder, ax_folder))
        if include_perturb_auf and (tri_download_flag or not
                                    os.path.isfile('{}/trilegal_auf_simulation_bright.dat'
                                                   .format(ax_folder))):
            download_trilegal_simulation(ax_folder, tri_set_name, ax1, ax2, tri_filt_num,
                                         auf_region_frame, tri_maglim_bright,
                                         total_objs=tri_num_bright)
            os.system('mv {}/trilegal_auf_simulation.dat {}/trilegal_auf_simulation_bright.dat'
                      .format(ax_folder, ax_folder))

        if include_perturb_auf:
            sky_cut = _load_single_sky_slice(auf_folder, '', i, modelrefinds[2, :], use_memmap_files)
            if compute_local_density:
                # TODO: avoid np.arange by first iterating an np.sum(sky_cut)
                # and pre-generating a memmapped sub-array, and looping over
                # putting the correct indices into place.
                med_index_slice = np.arange(0, len(local_N))[sky_cut]
            a_photo_cut = a_tot_photo[sky_cut]
            if compute_local_density:
                a_astro_cut = a_tot_astro[sky_cut]

        for j in range(len(filters)):
            filt = filters[j]

            filt_folder = '{}/{}'.format(ax_folder, filt)
            if not os.path.exists(filt_folder):
                os.makedirs(filt_folder, exist_ok=True)

            if include_perturb_auf:
                good_mag_slice = ~np.isnan(a_photo_cut[:, j])
                a_photo = a_photo_cut[good_mag_slice, j]
                if len(a_photo) == 0:
                    arraylengths[j, i] = 0
                    # If no sources in this AUF-filter combination, we need to
                    # fake some dummy variables for use in the 3/4-D grids below.
                    # See below, in include_perturb_auf is False, for meanings.
                    num_N_mag = 1
                    Frac = np.zeros((1, num_N_mag), float, order='F')
                    np.save('{}/frac.npy'.format(filt_folder), Frac)
                    Flux = np.zeros(num_N_mag, float, order='F')
                    np.save('{}/flux.npy'.format(filt_folder), Flux)
                    offset = np.zeros((len(r)-1, num_N_mag), float, order='F')
                    offset[0, :] = 1 / (2 * np.pi * (r[0] + dr[0]/2) * dr[0])
                    np.save('{}/offset.npy'.format(filt_folder), offset)
                    cumulative = np.ones((len(r)-1, num_N_mag), float, order='F')
                    np.save('{}/cumulative.npy'.format(filt_folder), cumulative)
                    fourieroffset = np.ones((len(rho)-1, num_N_mag), float, order='F')
                    np.save('{}/fourier.npy'.format(filt_folder), fourieroffset)
                    Narray = np.array([[1]], float)
                    np.save('{}/N.npy'.format(filt_folder), Narray)
                    magarray = np.array([[1]], float)
                    np.save('{}/mag.npy'.format(filt_folder), magarray)
                    continue
                if compute_local_density:
                    localN = calculate_local_density(
                        a_astro_cut[good_mag_slice], a_tot_astro, a_tot_photo[:, j],
                        auf_folder, cat_folder, density_radius, density_mags[j],
                        memmap_slice_arrays, use_memmap_files)
                    # Because we always calculate the density from the full
                    # catalogue, using just the astrometry, we should be able
                    # to just over-write this N times if there happen to be N
                    # good detections of a source.
                    index_slice = med_index_slice[good_mag_slice]
                    for ii in range(len(index_slice)):
                        local_N[index_slice[ii], j] = localN[ii]
                else:
                    localN = np.load('{}/local_N.npy'.format(auf_folder),
                                     mmap_mode='r')[sky_cut][good_mag_slice, j]
                if fit_gal_flag:
                    Narray = create_single_perturb_auf(
                        ax_folder, auf_points, filters[j], r, dr, rho, drho, j0s, num_trials,
                        psf_fwhms[j], tri_filt_names[j], density_mags[j], a_photo, localN, d_mag,
                        delta_mag_cuts, dd_params, l_cut, run_fw, run_psf, mag_h_params,
                        fit_gal_flag, cmau_array, wavs[j], z_maxs[j], nzs[j], alpha0, alpha1,
                        alpha_weight, ab_offsets[j], filter_names[j], al_avs[j])
                else:
                    Narray = create_single_perturb_auf(
                        ax_folder, auf_points, filters[j], r, dr, rho, drho, j0s, num_trials,
                        psf_fwhms[j], tri_filt_names[j], density_mags[j], a_photo, localN, d_mag,
                        delta_mag_cuts, dd_params, l_cut, run_fw, run_psf, mag_h_params,
                        fit_gal_flag)
            else:
                # Without the simulations to force local normalising density N or
                # individual source brightness magnitudes, we can simply combine
                # all data into a single "bin".
                num_N_mag = 1
                # In cases where we do not want to use the perturbation AUF component,
                # we currently don't have separate functions, but instead set up dummy
                # functions and variables to pass what mathematically amounts to
                # "nothing" through the cross-match. Here we would use fortran
                # subroutines to create the perturbation simulations, so we make
                # f-ordered dummy parameters.
                Frac = np.zeros((1, num_N_mag), float, order='F')
                np.save('{}/frac.npy'.format(filt_folder), Frac)
                Flux = np.zeros(num_N_mag, float, order='F')
                np.save('{}/flux.npy'.format(filt_folder), Flux)
                # Remember that r is bins, so the evaluations at bin middle are one
                # shorter in length.
                offset = np.zeros((len(r)-1, num_N_mag), float, order='F')
                # Fix offsets such that the probability density function looks like
                # a delta function, such that a two-dimensional circular coordinate
                # integral would evaluate to one at every point, cf. ``cumulative``.
                offset[0, :] = 1 / (2 * np.pi * (r[0] + dr[0]/2) * dr[0])
                np.save('{}/offset.npy'.format(filt_folder), offset)
                # The cumulative integral of a delta function is always unity.
                cumulative = np.ones((len(r)-1, num_N_mag), float, order='F')
                np.save('{}/cumulative.npy'.format(filt_folder), cumulative)
                # The Hankel transform of a delta function is a flat line; this
                # then preserves the convolution being multiplication in fourier
                # space, as F(x) x 1 = F(x), similar to how f(x) * d(0) = f(x).
                fourieroffset = np.ones((len(rho)-1, num_N_mag), float, order='F')
                np.save('{}/fourier.npy'.format(filt_folder), fourieroffset)
                # Both normalising density and magnitude arrays can be proxied
                # with a dummy parameter, as any minimisation of N-m distance
                # must pick the single value anyway.
                Narray = np.array([[1]], float)
                np.save('{}/N.npy'.format(filt_folder), Narray)
                magarray = np.array([[1]], float)
                np.save('{}/mag.npy'.format(filt_folder), magarray)
            arraylengths[j, i] = len(Narray)

    if include_perturb_auf:
        longestNm = np.amax(arraylengths)

        if use_memmap_files:
            Narrays = np.lib.format.open_memmap('{}/narrays.npy'.format(auf_folder), mode='w+',
                                                dtype=float, shape=(longestNm, len(filters),
                                                len(auf_points)), fortran_order=True)
            Narrays[:, :, :] = -1
        else:
            Narrays = np.full(dtype=float, shape=(longestNm, len(filters), len(auf_points)),
                              order='F', fill_value=-1)

        if use_memmap_files:
            magarrays = np.lib.format.open_memmap('{}/magarrays.npy'.format(auf_folder), mode='w+',
                                                dtype=float, shape=(longestNm, len(filters),
                                                len(auf_points)), fortran_order=True)
            magarrays[:, :, :] = -1
        else:
            magarrays = np.full(dtype=float, shape=(longestNm, len(filters), len(auf_points)),
                                order='F', fill_value=-1)

        for i in range(len(auf_points)):
            ax1, ax2 = auf_points[i]
            ax_folder = '{}/{}/{}'.format(auf_folder, ax1, ax2)
            for j in range(len(filters)):
                if arraylengths[j, i] == 0:
                    continue
                filt = filters[j]
                filt_folder = '{}/{}'.format(ax_folder, filt)
                Narray = np.load('{}/N.npy'.format(filt_folder))
                magarray = np.load('{}/mag.npy'.format(filt_folder))
                Narrays[:arraylengths[j, i], j, i] = Narray
                magarrays[:arraylengths[j, i], j, i] = magarray

    # Once the individual AUF simulations are saved, we also need to calculate
    # the indices each source references when slicing into the 4-D cubes
    # created by [1-D array] x N-m combination x filter x sky position iteration.

    print('Creating perturbation AUFs filter indices for catalogue "{}"...'.format(which_cat))
    sys.stdout.flush()

    for cnum in range(0, mem_chunk_num):
        lowind = np.floor(n_sources*cnum/mem_chunk_num).astype(int)
        highind = np.floor(n_sources*(cnum+1)/mem_chunk_num).astype(int)
        if include_perturb_auf:
            a = np.load('{}/con_cat_photo.npy'.format(cat_folder), mmap_mode='r')[lowind:highind]
            local_N = np.load('{}/local_N.npy'.format(auf_folder), mmap_mode='r')[lowind:highind]
        magref = np.load('{}/magref.npy'.format(cat_folder), mmap_mode='r')[lowind:highind]
        # As we chunk in even steps through the files this is simple for now,
        # but could be replaced with a more complex mapping in the future.
        indexmap = np.arange(lowind, highind, 1)

        if include_perturb_auf:
            for i in range(0, len(a)):
                axind = modelrefinds[2, indexmap[i]]
                filterind = magref[i]
                Nmind = np.argmin((local_N[i, filterind] - Narrays[:arraylengths[filterind, axind],
                                                                   filterind, axind])**2 +
                                  (a[i, filterind] - magarrays[:arraylengths[filterind, axind],
                                                               filterind, axind])**2)
                modelrefinds[0, indexmap[i]] = Nmind
        else:
            # For the case that we do not use the perturbation AUF component,
            # our dummy N-m files are all one-length arrays, so we can
            # trivially index them, regardless of specifics.
            modelrefinds[0, indexmap] = 0

        # The mapping of which filter to use is straightforward: simply pick
        # the filter index of the "best" filter for each source, from magref.
        modelrefinds[1, indexmap] = magref

    if delta_mag_cuts is None:
        n_fracs = 2  # TODO: generalise once delta_mag_cuts is user-inputtable.
    else:
        n_fracs = len(delta_mag_cuts)
    # Create the 4-D grids that house the perturbation AUF fourier-space
    # representation.
    create_auf_params_grid(auf_folder, auf_points, filters, 'fourier', use_memmap_files,
                           len(rho)-1, arraylengths)
    # Create the estimated levels of flux contamination and fraction of
    # contaminated source grids.
    create_auf_params_grid(auf_folder, auf_points, filters, 'frac', use_memmap_files,
                           n_fracs, arraylengths)
    create_auf_params_grid(auf_folder, auf_points, filters, 'flux', use_memmap_files,
                           arraylengths=arraylengths)

    if include_perturb_auf:
        del Narrays, magarrays

        if use_memmap_files:
          os.remove('{}/narrays.npy'.format(auf_folder))
          os.remove('{}/magarrays.npy'.format(auf_folder))

          # Delete sky slices used to make fourier cutouts.
          os.system('rm {}/*temporary_sky_slice*.npy'.format(auf_folder))
          os.system('rm {}/_small_sky_slice.npy'.format(auf_folder))

    return modelrefinds


def download_trilegal_simulation(tri_folder, tri_filter_set, ax1, ax2, mag_num, region_frame,
                                 mag_lim, total_objs=1.5e6):
    '''
    Get a single Galactic sightline TRILEGAL simulation of an appropriate sky
    size, and save it in a folder for use in the perturbation AUF simulations.

    Parameters
    ----------
    tri_folder : string
        The location of the folder into which to save the TRILEGAL file.
    tri_filter_set : string
        The name of the filterset, as given by the TRILEGAL input form.
    ax1 : float
        The first axis position of the sightline to be simulated, in the frame
        determined by ``region_frame``.
    ax2 : float
        The second axis position of the TRILEGAL sightline.
    mag_num : integer
        The zero-indexed filter number in the ``tri_filter_set`` list of filters
        which decides the limiting magnitude down to which tosimulate the
        Galactic sources.
    region_frame : string
        Frame, either equatorial or galactic, of the cross-match being performed,
        indicating whether ``ax1`` and ``ax2`` are in Right Ascension and
        Declination or Galactic Longitude and Latitude.
    mag_lim : float
        Magnitude down to which to generate sources for the simulation.
    total_objs : integer, optional
        The approximate number of objects to simulate in a TRILEGAL sightline,
        affecting how large an area to request a simulated Galactic region of.
    '''
    areaflag = 0
    triarea = 0.001
    tri_name = 'trilegal_auf_simulation'
    galactic_flag = True if region_frame == 'galactic' else False
    while areaflag == 0:
        _ = get_trilegal(tri_name, ax1, ax2, folder=tri_folder, galactic=galactic_flag,
                         filterset=tri_filter_set, area=triarea, maglim=mag_lim, magnum=mag_num)
        f = open('{}/{}.dat'.format(tri_folder, tri_name), "r")
        contents = f.readlines()
        f.close()
        # Two comment lines; one at the top and one at the bottom - we add a
        # third in a moment, however
        nobjs = len(contents) - 2
        # If too few stars then increase by factor 10 and loop, or scale to give
        # about 1.5 million stars and come out of area increase loop --
        # simulations can't be more than 10 sq deg, so accept if that's as large
        # as we can go.
        if nobjs < 10000 and triarea < 10:
            triarea = min(10, triarea*10)
        else:
            triarea = min(10, triarea / nobjs * total_objs)
            areaflag = 1
        os.system('rm {}/{}.dat'.format(tri_folder, tri_name))
    av_inf = get_trilegal(tri_name, ax1, ax2, folder=tri_folder, galactic=galactic_flag,
                          filterset=tri_filter_set, area=triarea, maglim=mag_lim, magnum=mag_num)
    f = open('{}/{}.dat'.format(tri_folder, tri_name), "r")
    contents = f.readlines()
    f.close()
    contents.insert(0, '#area = {} sq deg\n#Av at infinity = {}\n'.format(triarea, av_inf))
    f = open('{}/{}.dat'.format(tri_folder, tri_name), "w")
    contents = "".join(contents)
    f.write(contents)
    f.close()


def calculate_local_density(a_astro, a_tot_astro, a_tot_photo, auf_folder, cat_folder,
                            density_radius, density_mag, memmap_slice_arrays,
                            use_memmap_files):
    '''
    Calculates the number of sources above a given brightness within a specified
    radius of each source in a catalogue, to provide a local density for
    normalisation purposes.

    Parameters
    ----------
    a_astro : numpy.ndarray
        Sub-set of astrometric portion of total catalogue, for which local
        densities are to be calculated.
    a_tot_astro : numpy.ndarray
        Full astrometric catalogue, from which all potential sources above
        ``density_mag`` and coeval with ``a_astro`` sources are to be extracted.
    a_tot_photo : numpy.ndarray
        The photometry of the full catalogue, matching ``a_tot_astro``.
    auf_folder : string
        The folder designated to contain the perturbation AUF component related
        data for this catalogue.
    cat_folder : string
        The location of the catalogue files for this dataset.
    density_radius : float
        The radius, in degrees, out to which to consider the number of sources
        for the normalising density.
    density_mag : float
        The brightness, in magnitudes, above which to count sources for density
        purposes.
    memmap_slice_arrays : list of numpy.ndarray
        List of the memmap sky slice arrays, to be used in the loading of the
        rectangular sky patch.
    use_memmap_files : boolean
        When set to True, memory mapped files are used for several internal
        arrays. Reduces memory consumption at the cost of increased I/O
        contention.

    Returns
    -------
    count_density : numpy.ndarray
        The number of sources per square degree near to each source in
        ``a_astro`` that are above ``density_mag`` in ``a_tot_astro``.
    '''

    min_lon, max_lon = np.amin(a_astro[:, 0]), np.amax(a_astro[:, 0])
    min_lat, max_lat = np.amin(a_astro[:, 1]), np.amax(a_astro[:, 1])

    memmap_slice_arrays_2 = []
    if use_memmap_files:
        for n in ['1', '2', '3', '4', 'combined']:
            memmap_slice_arrays_2.append(np.lib.format.open_memmap(
                '{}/{}_temporary_sky_slice_{}.npy'.format(auf_folder, '2', n), mode='w+',
                dtype=bool, shape=(len(a_astro),)))
    else:
        for _ in range(5):
            memmap_slice_arrays_2.append(np.zeros(dtype=bool, shape=(len(a_astro),)))

    overlap_sky_cut = _load_rectangular_slice(auf_folder, '', a_tot_astro, min_lon,
                                              max_lon, min_lat, max_lat, density_radius,
                                              memmap_slice_arrays)
    if use_memmap_files:
        cut = np.lib.format.open_memmap('{}/_temporary_slice.npy'.format(
            auf_folder), mode='w+', dtype=bool, shape=(len(a_tot_astro),))
    else:
        cut = np.zeros(dtype=bool, shape=(len(a_tot_astro),))
    di = max(1, len(cut) // 20)
    for i in range(0, len(a_tot_astro), di):
        cut[i:i+di] = overlap_sky_cut[i:i+di] & (a_tot_photo[i:i+di] <= density_mag)
    a_astro_overlap_cut = a_tot_astro[cut]
    a_photo_overlap_cut = a_tot_photo[cut]

    memmap_slice_arrays_3 = []
    if use_memmap_files:
        for n in ['1', '2', '3', '4', 'combined']:
            memmap_slice_arrays_3.append(np.lib.format.open_memmap(
                '{}/{}_temporary_sky_slice_{}.npy'.format(auf_folder, '3', n), mode='w+',
                dtype=bool, shape=(len(a_astro_overlap_cut),)))
    else:
        for _ in range(5):
            memmap_slice_arrays_3.append(np.zeros(dtype=bool, shape=(len(a_astro_overlap_cut),)))

    ax1_loops = np.linspace(min_lon, max_lon, 11)
    # Force the sub-division of the sky area in question to be 100 chunks, or
    # roughly square degree chunks, whichever is larger in area.
    if ax1_loops[1] - ax1_loops[0] < 1:
        ax1_loops = np.linspace(min_lon, max_lon,
                                int(np.ceil(max_lon - min_lon) + 1))
    ax2_loops = np.linspace(min_lat, max_lat, 11)
    if ax2_loops[1] - ax2_loops[0] < 1:
        ax2_loops = np.linspace(min_lat, max_lat,
                                int(np.ceil(max_lat - min_lat) + 1))
    full_counts = np.empty(len(a_astro), float)
    for ax1_start, ax1_end in zip(ax1_loops[:-1], ax1_loops[1:]):
        for ax2_start, ax2_end in zip(ax2_loops[:-1], ax2_loops[1:]):
            small_sky_cut = _load_rectangular_slice(auf_folder, 'small_', a_astro, ax1_start,
                                                    ax1_end, ax2_start, ax2_end, 0,
                                                    memmap_slice_arrays_2)
            a_astro_small = a_astro[small_sky_cut]
            if len(a_astro_small) == 0:
                continue

            overlap_sky_cut = _load_rectangular_slice(auf_folder, '', a_astro_overlap_cut,
                                                      ax1_start, ax1_end, ax2_start, ax2_end,
                                                      density_radius, memmap_slice_arrays_3)
            if use_memmap_files:
                cut = np.lib.format.open_memmap('{}/_temporary_slice.npy'.format(
                    auf_folder), mode='w+', dtype=bool, shape=(len(a_astro_overlap_cut),))
            else:
                cut = np.zeros(dtype=bool, shape=(len(a_astro_overlap_cut),))
            di = max(1, len(cut) // 20)
            for i in range(0, len(a_astro_overlap_cut), di):
                cut[i:i+di] = (overlap_sky_cut[i:i+di] &
                               (a_photo_overlap_cut[i:i+di] <= density_mag))
            a_astro_overlap_cut_small = a_astro_overlap_cut[cut]

            if len(a_astro_overlap_cut_small) > 0:
                counts = paf.get_density(a_astro_small[:, 0], a_astro_small[:, 1],
                                         a_astro_overlap_cut_small[:, 0],
                                         a_astro_overlap_cut_small[:, 1], density_radius)
                # If objects return with zero bright sources in their error circle,
                # like in the else below we force at least themselves to be in the
                # circle, slightly over-representing any object below the
                # brightness cutoff, but 1/area is still a very low density.
                counts[counts == 0] = 1
                full_counts[small_sky_cut] = counts
            else:
                # If we have sources to check the surrounding density of, but
                # no bright sources around them, just set them to be alone
                # in the error circle, slightly over-representing bright objects
                # but still giving them a very low normalising sky density.
                full_counts[small_sky_cut] = 1
    min_lon, max_lon = np.amin(a_astro_overlap_cut[:, 0]), np.amax(a_astro_overlap_cut[:, 0])
    min_lat, max_lat = np.amin(a_astro_overlap_cut[:, 1]), np.amax(a_astro_overlap_cut[:, 1])

    circle_overlap_area = paf.get_circle_area_overlap(a_astro[:, 0], a_astro[:, 1], density_radius,
                                                      min_lon, max_lon, min_lat, max_lat)

    count_density = full_counts / circle_overlap_area

    if use_memmap_files:
        os.system('rm {}/_temporary_slice.npy'.format(auf_folder))
    else:
        del cut

    return count_density


def create_single_perturb_auf(tri_folder, auf_point, filt, r, dr, rho, drho, j0s, num_trials,
                              psf_fwhm, header, density_mag, a_photo, localN, d_mag, mag_cut,
                              dd_params, l_cut, run_fw, run_psf, mag_h_params, fit_gal_flag,
                              cmau_array=None, wav=None, z_max=None, nz=None, alpha0=None,
                              alpha1=None, alpha_weight=None, ab_offset=None, filter_name=None,
                              al_av=None):
    r'''
    Creates the associated parameters for describing a single perturbation AUF
    component, for a single sky position.

    Parameters
    ----------
    tri_folder : string
        Folder where the TRILEGAL datafile is stored, and where the individual
        filter-specific perturbation AUF simulations should be saved.
    auf_point : numpy.ndarray
        The orthogonal sky coordinates of the simulated AUF component.
    filt : float
        Filter for which to simulate the AUF component.
    r : numpy.ndarray
        Array of real-space positions.
    dr : numpy.ndarray
        Array of the bin sizes of each ``r`` position.
    rho : numpy.ndarray
        Fourier-space coordinates at which to sample the fourier transformation
        of the distribution of perturbations due to blended sources.
    drho : numpy.ndarray
        Bin widths of each ``rho`` coordinate.
    j0s : numpy.ndarray
        The Bessel Function of First Kind of Zeroth Order, evaluated at all
        ``r``-``rho`` combinations.
    num_trials : integer
        The number of realisations of blended contaminant sources to draw
        when simulating perturbations of source positions.
    psf_fwhm : float
        The full-width at half maxima of the ``filt`` filter.
    header : float
        The filter name, as given by the TRILEGAL datafile, for this simulation.
    density_mag : float
        The limiting magnitude above which to consider local normalising densities,
        corresponding to the ``filt`` bandpass.
    a_photo : numpy.ndarray
        The photometry of each source for which simulated perturbations should be
        made.
    localN : numpy.ndarray
        The local normalising densities for each source.
    d_mag : float
        The interval at which to bin the magnitudes of a given set of objects,
        for the creation of the appropriate brightness/density combinations to
        simulate.
    mag_cut : numpy.ndarray or list of floats
        The magnitude offsets -- or relative fluxes -- above which to keep track of
        the fraction of objects suffering from a contaminating source.
    dd_params : numpy.ndarray
        Polynomial fits for the various parameters controlling the background
        limited PSF-fit algorithm for centroid perturbations.
    l_cut : numpy.ndarray or list
        Relative flux cutoffs for which algorithm to use in the background
        limited PSF-fit algorithm case.
    run_fw : bool
        Flag indicating whether to run the "flux-weighted" version of the
        perturbation algorithm.
    run_psf : bool
        Flag indicating whether to run the "background-dominated PSF" version
        of the perturbation algorithm.
    mag_h_params : numpy.ndarray
        Array, of shape ``(N, 5)``, containing the pre-determined values of the
        magnitude-perturbation weighting relationship for a series of Galactic
        sightlines.
    fit_gal_flag : bool
        Flag to indicate whether to simulate galaxy counts for the purposes of
        simulating the perturbation component of the AUF.
    cmau_array : numpy.ndarray, optional
        Array holding the c/m/a/u values that describe the parameterisation
        of the Schechter functions with wavelength, following Wilson (2022, RNAAS,
        6, 60) [1]_. Shape should be `(5, 2, 4)`, with 5 parameters for both blue
        and red galaxies.
    wav : float, optional
        Wavelength, in microns, of the filter of the current observations.
    z_max : float, optional
        Maximum redshift to simulate differential galaxy counts out to.
    nz : int, optional
        Number of redshifts to simulate, to dictate resolution of Schechter
        functions used to generate differential galaxy counts.
    alpha0 : list of numpy.ndarray or numpy.ndarray, optional
        Zero-redshift indices used to calculate Dirichlet SED coefficients,
        used within the differential galaxy count simulations. Should either be
        a two-element list or shape ``(2, 5)`` array. See [2]_ and [3]_ for
        more details.
    alpha1 : list of numpy.ndarray or numpy.ndarray, optional
        Dirichlet SED coefficients at z=1.
    alpha_weight : list of numpy.ndarray or numpy.ndarray, optional
        Weights used to derive the ``kcorrect`` coefficients within the
        galaxy count framework.
    ab_offset : float, optional
        The zero point difference between the chosen filter and the AB system,
        for conversion of simulated galaxy counts from AB magnitudes. Should
        be of the convention m = m_AB - ab_offset
    filter_name : string, optional
        The ``speclite`` style ``group_name-band_name`` name for the filter,
        for use in the creation of simulated galaxy counts.
    al_av : float
        Reddening vector for the filter, :math:`\frac{A_\lambda}{A_V}`.

    Returns
    -------
    count_array : numpy.ndarray
        The simulated local normalising densities that were used to simulate
        potential perturbation distributions.

    References
    ----------
    .. [1] Wilson T. J. (2022), RNAAS, 6, 60
    .. [2] Herbel J., Kacprzak T., Amara A., et al. (2017), JCAP, 8, 35
    .. [3] Blanton M. R., Roweis S. (2007), AJ, 133, 734

    '''
    # TODO: extend to allow a Galactic source model that doesn't depend on TRILEGAL
    tri_name = 'trilegal_auf_simulation'
    dens_hist_tri, model_mags, model_mag_mids, model_mags_interval, _, av_inf = make_tri_counts(
        tri_folder, tri_name, header, d_mag)

    log10y_tri = -np.inf * np.ones_like(dens_hist_tri)
    log10y_tri[dens_hist_tri > 0] = np.log10(dens_hist_tri[dens_hist_tri > 0])

    mag_slice = (model_mags+model_mags_interval <= density_mag)
    tri_count = np.sum(10**log10y_tri[mag_slice] * model_mags_interval[mag_slice])

    if fit_gal_flag:
        al_inf = al_av * av_inf
        z_array = np.linspace(0, z_max, nz)
        gal_dens = create_galaxy_counts(cmau_array, model_mag_mids, z_array, wav, alpha0, alpha1,
                                        alpha_weight, ab_offset, filter_name, al_inf)
        max_mag_bin = np.argwhere(model_mags+model_mags_interval <= density_mag)[0][-1] + 1
        gal_count = np.sum(gal_dens[:max_mag_bin]*model_mags_interval[:max_mag_bin])
        log10y_gal = -np.inf * np.ones_like(log10y_tri)
        log10y_gal[gal_dens > 0] = np.log10(gal_dens[gal_dens > 0])
    else:
        gal_count = 0
        log10y_gal = -np.inf * np.ones_like(log10y_tri)

        # If we're not generating galaxy counts, we have to solely rely on
        # TRILEGAL counting statistics, so we only want to keep populated bins.
        hc = np.where(dens_hist_tri > 0)[0]
        model_mag_mids = model_mag_mids[hc]
        model_mags_interval = model_mags_interval[hc]
        log10y_tri = log10y_tri[hc]

    model_count = tri_count + gal_count
    log10y = np.log10(10**log10y_tri + 10**log10y_gal)

    # Set a magnitude bin width of 0.25 mags, to avoid oversampling.
    dmag = 0.25
    mag_min = dmag * np.floor(np.amin(a_photo)/dmag)
    mag_max = dmag * np.ceil(np.amax(a_photo)/dmag)
    magbins = np.arange(mag_min, mag_max+1e-10, dmag)
    # For local densities, we want a percentage offset, given that we're in
    # logarithmic bins, accepting a log-difference maximum. This is slightly
    # lop-sided, but for 20% results in +18%/-22% limits, which is fine.
    dlogN = 0.2
    logNvals = np.log(localN)
    logN_min = dlogN * np.floor(np.amin(logNvals)/dlogN)
    logN_max = dlogN * np.ceil(np.amax(logNvals)/dlogN)
    logNbins = np.arange(logN_min, logN_max+1e-10, dlogN)

    counts, logNbins, magbins = np.histogram2d(logNvals, a_photo, bins=[logNbins, magbins])
    Ni, magi = np.where(counts > 0)
    mag_array = 0.5*(magbins[1:]+magbins[:-1])[magi]
    count_array = np.exp(0.5*(logNbins[1:]+logNbins[:-1])[Ni])

    R = 1.185 * psf_fwhm

    s_flux = 10**(-1/2.5 * mag_array)
    lb_ind = mff.find_nearest_point(auf_point[:, 0], auf_point[:, 1],
                                    mag_h_params[:, 3], mag_h_params[:, 4])[0]
    a_snr = mag_h_params[lb_ind, 0]
    b_snr = mag_h_params[lb_ind, 1]
    c_snr = mag_h_params[lb_ind, 2]
    snr = s_flux / np.sqrt(c_snr * s_flux + b_snr + (a_snr * s_flux)**2)

    B = 0.05
    dm_max = _calculate_magnitude_offsets(count_array, mag_array, B, snr, model_mag_mids, log10y,
                                          model_mags_interval, R, model_count)

    seed = np.random.default_rng().choice(100000, size=(paf.get_random_seed_size(),
                                                        len(count_array)))

    psf_sig = psf_fwhm / (2 * np.sqrt(2 * np.log(2)))

    if run_fw:
        Frac_fw, Flux_fw, fourieroffset_fw, offset_fw, cumulative_fw = paf.perturb_aufs(
            count_array, mag_array, r[:-1]+dr/2, dr, r, j0s.T,
            model_mag_mids, model_mags_interval, log10y, model_count,
            (dm_max/d_mag).astype(int), mag_cut, R, psf_sig, num_trials, seed, dd_params,
            l_cut, 'fw')
    if run_psf:
        Frac_psf, Flux_psf, fourieroffset_psf, offset_psf, cumulative_psf = paf.perturb_aufs(
            count_array, mag_array, r[:-1]+dr/2, dr, r, j0s.T,
            model_mag_mids, model_mags_interval, log10y, model_count,
            (dm_max/d_mag).astype(int), mag_cut, R, psf_sig, num_trials, seed, dd_params,
            l_cut, 'psf')

    if run_fw and run_psf:
        h = 1 - np.sqrt(1 - min(1, a_snr**2 * snr**2))
        Flux = h * Flux_fw + (1 - h) * Flux_psf
        h = h.reshape(1, -1)
        Frac = h * Frac_fw + (1 - h) * Frac_psf
        offset = h * offset_fw + (1 - h) * offset_psf
        cumulative = h * cumulative_fw + (1 - h) * cumulative_psf
        fourieroffset = h * fourieroffset_fw + (1 - h) * fourieroffset_psf
    elif run_fw:
        Flux = Flux_fw
        Frac = Frac_fw
        offset = offset_fw
        cumulative = cumulative_fw
        fourieroffset = fourieroffset_fw
    else:
        Flux = Flux_psf
        Frac = Frac_psf
        offset = offset_psf
        cumulative = cumulative_psf
        fourieroffset = fourieroffset_psf

    np.save('{}/{}/frac.npy'.format(tri_folder, filt), Frac)
    np.save('{}/{}/flux.npy'.format(tri_folder, filt), Flux)
    np.save('{}/{}/offset.npy'.format(tri_folder, filt), offset)
    np.save('{}/{}/cumulative.npy'.format(tri_folder, filt), cumulative)
    np.save('{}/{}/fourier.npy'.format(tri_folder, filt), fourieroffset)
    np.save('{}/{}/N.npy'.format(tri_folder, filt), count_array)
    np.save('{}/{}/mag.npy'.format(tri_folder, filt), mag_array)

    return count_array


def make_tri_counts(trifolder, trifilename, trifiltname, dm):
    """
    Combine TRILEGAL simulations for a given line of sight in the Galaxy, using
    both a "bright" simulation, with a brighter magnitude limit that allows for
    more detail in the lower-number statistic bins, and a "faint" or full
    simulation down to the faint limit to capture the full source count
    distribution for the filter.

    Parameters
    ----------
    trifolder : string
        Location on disk into which to save TRILEGAL simulations.
    trifilename : string
        Name to save TRILEGAL simulation files to, to which "_bright" and
        "_faint" will be appended for the two runs respectively.
    trifiltname : string
        The individual filter within ``trifilterset`` being used for generating
        differential source counts.
    dm : float
        Width of the bins into which to place simulated magnitudes.

    Returns
    -------
    dens : numpy.ndarray
        The probability density function of the resulting merged differential
        source counts from the two TRILEGAL simulations, weighted by their
        counting-statistic bin uncertainties.
    tri_mags : numpy.ndarray
        The left-hand bin edges of all bins used to generate ``dens``.
    tri_mags_mids : numpy.ndarray
        Middle of each bin generating ``dens``.
    dtri_mags : numpy.ndarray
        Bin widths of all bins corresponding to each element of ``dens``.
    uncert : numpy.ndarray
        Propagated Poissonian uncertainties of the PDF of ``dens``, using the
        weighted average of the individual uncertainties of each run for every
        bin in ``dens``.
    tri_av : float
        The largest of all reported V-band extinctions at infinity across all
        of the simulations used in the generation of the source count histograms.
    """
    f = open('{}/{}_faint.dat'.format(trifolder, trifilename), "r")
    area_line = f.readline()
    av_line = f.readline()
    f.close()
    # #area = {} sq deg, #Av at infinity = {} should be the first two lines, so
    # just split that by whitespace
    bits = area_line.split(' ')
    tri_area_faint = float(bits[2])
    bits = av_line.split(' ')
    tri_av_inf_faint = float(bits[4])
    tri_faint = np.genfromtxt('{}/{}_faint.dat'.format(trifolder, trifilename), delimiter=None,
                              names=True, comments='#', skip_header=2, usecols=[trifiltname, 'Av'])

    f = open('{}/{}_bright.dat'.format(trifolder, trifilename), "r")
    area_line = f.readline()
    av_line = f.readline()
    f.close()
    bits = area_line.split(' ')
    tri_area_bright = float(bits[2])
    bits = av_line.split(' ')
    tri_av_inf_bright = float(bits[4])
    tri_bright = np.genfromtxt('{}/{}_bright.dat'.format(trifolder, trifilename), delimiter=None,
                               names=True, comments='#', skip_header=2, usecols=[trifiltname, 'Av'])

    tridata_faint = tri_faint[:][trifiltname]
    tri_av_faint = np.amax(tri_faint[:]['Av'])
    del tri_faint
    tridata_bright = tri_bright[:][trifiltname]
    tri_av_bright = np.amax(tri_bright[:]['Av'])
    del tri_bright
    minmag = dm * np.floor(min(np.amin(tridata_faint), np.amin(tridata_bright))/dm)
    maxmag = dm * np.ceil(max(np.amax(tridata_faint), np.amax(tridata_bright))/dm)
    hist, tri_mags = np.histogram(tridata_faint, bins=np.arange(minmag, maxmag+1e-10, dm))
    hc_faint = hist > 3
    dens_faint = hist / np.diff(tri_mags) / tri_area_faint
    dens_uncert_faint = np.sqrt(hist) / np.diff(tri_mags) / tri_area_faint
    dens_uncert_faint[dens_uncert_faint == 0] = 1e10

    hist, tri_mags = np.histogram(tridata_bright, bins=tri_mags)
    hc_bright = hist > 3
    dens_bright = hist / np.diff(tri_mags) / tri_area_bright
    dens_uncert_bright = np.sqrt(hist) / np.diff(tri_mags) / tri_area_bright
    dens_uncert_bright[dens_uncert_bright == 0] = 1e10
    # Assume that the number of objects in the bright dataset is truncated such
    # that it should be most dense at its faintest magnitude, and ignore cases
    # where objects may have "scattered" outside of that limit. These are most
    # likely to be objects in magnitudes that don't define the TRILEGAL cutoff,
    # where differential reddening can make a few of them slightly fainter than
    # average.
    bright_mag = tri_mags[1:][np.argmax(hist)]
    dens_uncert_bright[tri_mags[1:] > bright_mag] = 1e10

    w_f, w_b = 1 / dens_uncert_faint**2, 1 / dens_uncert_bright**2
    dens = (dens_bright * w_b + dens_faint * w_f) / (w_b + w_f)
    dens_uncert = np.sqrt(1 / (w_b + w_f))

    hc = hc_bright | hc_faint

    dens = dens[hc]
    dtri_mags = np.diff(tri_mags)[hc]
    tri_mags_mids = (tri_mags[:-1]+np.diff(tri_mags))[hc]
    tri_mags = tri_mags[:-1][hc]
    uncert = dens_uncert[hc]

    tri_av = max((tri_av_bright, tri_av_inf_bright, tri_av_faint, tri_av_inf_faint))

    return dens, tri_mags, tri_mags_mids, dtri_mags, uncert, tri_av


def _calculate_magnitude_offsets(count_array, mag_array, B, snr, model_mag_mids, log10y,
                                 model_mags_interval, R, N_norm):
    '''
    Derive minimum relative fluxes, or largest magnitude offsets, down to which
    simulated perturbers need to be simulated, based on both considerations of
    their flux relative to the noise of the primary object and the fraction of
    simulations in which there is no simulated perturbation.

    Parameters
    ----------
    count_array : numpy.ndarray
        Local normalising densities of simulations.
    mag_array : numpy.ndarray
        Magnitudes of central objects to have perturbations simulated for.
    B : float
        Fraction of ``snr`` the flux of the perturber should be; e.g. for
        1/20th ``B`` should be 0.05.
    snr : numpy.ndarray
        Theoretical signal-to-noise ratios of each object in ``mag_array``.
    model_mag_mids : numpy.ndarray
        Model magnitudes for simulated densities of background objects.
    log10y : numpy.ndarray
        log-10 source densities of simulated objects in the given line of sight.
    model_mags_interval : numpy.ndarray
        Widths of the bins for each ``log10y``.
    R : float
        Radius of the PSF of the given simulation, in arcseconds.
    N_norm : float
        Normalising local density of simulations, to scale to each
        ``count_array``.

    Returns
    -------
    dm : numpy.ndarray
        Maximum magnitude offset required for simulations, based on SNR and
        empty simulation fraction.
    '''
    Flim = B / snr
    dm_max_snr = -2.5 * np.log10(Flim)

    dm_max_no_perturb = np.empty_like(mag_array)
    for i in range(len(mag_array)):
        q = model_mag_mids >= mag_array[i]
        _x = model_mag_mids[q]
        _y = 10**log10y[q] * model_mags_interval[q] * np.pi * (R/3600)**2 * count_array[i] / N_norm

        # Convolution of Poissonian distributions each with l_i is a Poissonian
        # with mean of sum_i l_i.
        lamb = np.cumsum(_y)
        # CDF of Poissonian is regularised gamma Q(floor(k + 1), lambda), and we
        # want k = 0; we wish to find the dm that gives sufficiently large lambda
        # that k = 0 only occurs <= x% of the time. If lambda is too small then
        # k = 0 is too likely. P(X <= 0; lambda) = exp(-lambda).
        # For 1% chance of no perturber we want 0.01 = exp(-lambda); rearranging
        # lambda = -ln(0.01).
        q = np.where(lamb >= -np.log(0.01))[0]
        if len(q) > 0:
            dm_max_no_perturb[i] = _x[q[0]] - mag_array[i]
        else:
            # In the case that we can't go deep enough in our simulated counts to
            # get <1% chance of no perturber, just do the best we can.
            dm_max_no_perturb[i] = _x[-1] - mag_array[i]

    dm = np.maximum(dm_max_snr, dm_max_no_perturb)

    return dm
