""" # Example for what if scenarios
    Runtime ~ 3-5h

    ## Importing modules
"""

import datetime
import copy
import sys

import pymc3 as pm
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

try:
    import covid19_inference_new as cov19
except ModuleNotFoundError:
    sys.path.append("../..")
    import covid19_inference_new as cov19



""" ## Data retrieval
"""
data_begin = datetime.datetime(2020, 3, 2)
jhu = cov19.data_retrieval.JHU()
jhu.download_all_available_data(force_download=True)
cum_cases = jhu.get_total(country="Germany", data_begin=data_begin)
new_cases = jhu.get_new(country="Germany", data_begin=data_begin)

""" ## Create changepoints

"""
def make_cp_list(factor_dict, date_end):

    # change points like in the paper
    cp_list = [
        # mild distancing
        dict(
            # account for new implementation where transients_day is centered, not begin
            pr_mean_date_transient=datetime.datetime(2020, 3, 10),
            pr_median_transient_len=3,
            pr_sigma_transient_len=0.3,
            pr_sigma_date_transient=3,
            pr_median_lambda=0.2,
            pr_sigma_lambda=0.5,
        ),
        # strong distancing
        dict(
            pr_mean_date_transient=datetime.datetime(2020, 3, 17),
            pr_median_transient_len=3,
            pr_sigma_transient_len=0.3,
            pr_sigma_date_transient=1,
            pr_median_lambda=1 / 8,
            pr_sigma_lambda=0.5,
        ),
        # contact ban
        dict(
            pr_mean_date_transient=datetime.datetime(2020, 3, 24),
            pr_median_transient_len=3,
            pr_sigma_transient_len=0.3,
            pr_sigma_date_transient=1,
            pr_median_lambda=1 / 16,
            pr_sigma_lambda=0.5,
        ),
    ]
    pr_median_transient_len = 3
    pr_sigma_transient_len = 0.3
    pr_sigma_date_transient = 1
    last_date = datetime.datetime(2020, 3, 24)
    while True:
        date = last_date + datetime.timedelta(days=7)
        if date > date_end: break
        if date in factor_dict.keys():
            pr_factor_to_previous = factor_dict[date][0]
            #print("use factor {} on {}".format(pr_factor_to_previous, date))
            pr_sigma_lambda=factor_dict[date][1]
        else:
            pr_factor_to_previous = 1
            pr_sigma_lambda = 0.15

        
        cp = dict(
            pr_mean_date_transient=date,
            pr_sigma_lambda = pr_sigma_lambda,
            pr_median_transient_len=pr_median_transient_len,
            pr_sigma_transient_len=pr_sigma_transient_len,
            pr_sigma_date_transient=pr_sigma_date_transient,
            relative_to_previous=True,
            pr_factor_to_previous = pr_factor_to_previous
        )
        cp_list.append(cp)
        last_date = date
    
    return cp_list

cp_a = make_cp_list({datetime.datetime(2020, 5, 12):[2, 0.01],
                     datetime.datetime(2020, 5, 5):[1, 0.02]}, datetime.datetime(2020, 5, 12))
cp_b = make_cp_list({datetime.datetime(2020, 5, 12):[1.5, 0.01],
                     datetime.datetime(2020, 5, 5):[1, 0.02]}, datetime.datetime(2020, 5, 12))
cp_c = make_cp_list({datetime.datetime(2020, 5, 12):[1, 0.01],
                     datetime.datetime(2020, 5, 5):[1, 0.02]}, datetime.datetime(2020, 5, 12))

""" ## Put the model together
"""

def create_model(change_points, params_model):
    with cov19.Cov19Model(**params_model) as model:
        lambda_t_log = cov19.model.lambda_t_with_sigmoids(
            pr_median_lambda_0=0.4,
            pr_sigma_lambda_0=0.5,
            change_points_list=change_points,
            name_lambda_t="lambda_t"
        )

        mu = pm.Lognormal(
            name="mu",
            mu=np.log(1 / 8),
            sigma=0.2)
        
        pr_median_delay = 10

        prior_I = cov19.model.uncorrelated_prior_I(
            lambda_t_log=lambda_t_log,
            mu=mu,
            pr_median_delay=pr_median_delay)

        new_I_t =  cov19.model.SIR(
            lambda_t_log=lambda_t_log,
            mu=mu,
            pr_I_begin=prior_I)

        new_cases = cov19.model.delay_cases(
            cases = new_I_t,
            pr_mean_of_median=pr_median_delay,
            name_cases="delayed_cases",
        )
        
        new_cases= cov19.model.week_modulation(new_cases,name_cases="new_cases")
        
        cov19.model.student_t_likelihood(new_cases)
    return model


params_model = dict(
    new_cases_obs=new_cases,
    data_begin=data_begin,
    fcast_len=80,
    diff_data_sim=16,
    N_population=83e6,
)

mod_a = create_model(cp_a, params_model)
mod_b = create_model(cp_b, params_model)
mod_c = create_model(cp_c, params_model)

""" ## MCMC sampling
"""
import pickle
tr_a = pm.sample(model=mod_a, tune=1000, draws=1000, init="advi+adapt_diag")
tr_b = pm.sample(model=mod_b, tune=1000, draws=1000, init="advi+adapt_diag")
tr_c = pm.sample(model=mod_c, tune=1000, draws=1000, init="advi+adapt_diag")
pickle.dump([(mod_a, mod_b, mod_c), (tr_a, tr_b, tr_c)], open('../../data/what_if.pickled', 'wb'))

""" ## Plotting
    
    ### Save path
"""
try:
    # only works when called from python, not reliable in interactive ipython etc.
    os.chdir(os.path.dirname(__file__))
    save_path = "../../figures/what_if_"
except:
    # assume base directory
    save_path = "../../figures/what_if_"

""" ### Timeseries
    Timeseries overview, for now needs an offset variable to get cumulative cases

    #### English
"""
cov19.plot.set_rcparams(cov19.plot.get_rcparams_default())
cov19.plot.rcParams.draw_ci_50 = True
end = datetime.datetime(2020,6,14)
fig, axes = cov19.plot.timeseries_overview(
    mod_a,
    tr_a,
    offset=cum_cases[0],
    forecast_label="Pessimistic",
    forecast_heading=r"$\bf Scenarios\!:$",
    add_more_later=True,
    color="tab:red",

)
fig, axes = cov19.plot.timeseries_overview(
    mod_b,
    tr_b,
    axes=axes,
    offset=cum_cases[0],
    forecast_label="Neutral",
    color="tab:orange",
)
fig, axes = cov19.plot.timeseries_overview(
    mod_c,
    tr_c,
    axes=axes,
    offset=cum_cases[0],
    forecast_label="Optimistic",
    color="tab:green",
    end=end,
)
axes[0].set_ylim(-0.07,0.3)
axes[1].set_ylim(0,7500)
axes[2].set_ylim(0,220_000)

fig.savefig(save_path+'english_ts.pdf', dpi=300, bbox_inches="tight", pad_inches=0.05)
fig.savefig(save_path+'english_ts.png', dpi=300, bbox_inches="tight", pad_inches=0.05)

""" #### German
"""

cov19.plot.set_rcparams(cov19.plot.get_rcparams_default())
cov19.plot.rcParams.draw_ci_50 = True
cov19.plot.rcParams.locale = "de_DE"
cov19.plot.rcParams.date_format = "%-d. %b"

fig, axes = cov19.plot.timeseries_overview(
    mod_a,
    tr_a,
    offset=cum_cases[0],
    forecast_label="pessimistisch",
    forecast_heading=r"$\bf Szenarien\!:$",
    add_more_later=True,
    color="tab:red",
)


fig, axes = cov19.plot.timeseries_overview(
    mod_b,
    tr_b,
    axes=axes,
    offset=cum_cases[0],
    forecast_label="neutral",
    color="tab:orange",
)

fig, axes = cov19.plot.timeseries_overview(
    mod_c,
    tr_c,
    axes=axes,
    offset=cum_cases[0],
    forecast_label="optimistisch",
    color="tab:green",
    end=end
)

axes[0].set_ylim(-0.07,0.3)
axes[1].set_ylim(0,7500)
axes[2].set_ylim(0,220_000)

fig.savefig(save_path+'german_ts.pdf', dpi=300, bbox_inches="tight", pad_inches=0.05)
fig.savefig(save_path+'german_ts.png', dpi=300, bbox_inches="tight", pad_inches=0.05)

""" ### Distributions

	TODO
"""