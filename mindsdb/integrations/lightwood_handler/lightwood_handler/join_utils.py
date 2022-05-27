import copy
from itertools import product
import pandas as pd

from ts_utils import validate_ts_where_condition, find_time_filter, add_order_not_null, replace_time_filter, find_and_remove_time_filter, get_time_selects

from mindsdb_sql.parser.ast import Identifier, Constant, Operation, Select, BinaryOperation, BetweenOperation
from mindsdb_sql.parser.ast import OrderBy


def get_join_input(query, model, data_handler, data_side):
    data_handler_table = getattr(query.from_table, data_side).parts[-1]
    data_handler_cols = list(set([t.parts[-1] for t in query.targets]))

    data_query = Select(
        targets=[Identifier(col) for col in data_handler_cols],
        from_table=Identifier(data_handler_table),
        where=query.where,
        group_by=query.group_by,
        having=query.having,
        order_by=query.order_by,
        offset=query.offset,
        limit=query.limit
    )

    print(data_handler.query(data_query))
    model_input = pd.DataFrame.from_records(
        data_handler.query(data_query)['data_frame']
    )

    return model_input


def get_ts_join_input(query, model, data_handler, data_side):
    # TODO: bring in all TS tests from mindsdb_sql
    
    # step 1) query checks
    if query.order_by:
        raise PlanningException(
            f'Can\'t provide ORDER BY to time series predictor join query. Found: {query.order_by}.')

    if query.group_by or query.having or query.offset:
        raise PlanningException(f'Unsupported query to timeseries predictor: {str(query)}')

    if not model.problem_definition.timeseries_settings.is_timeseries:
        raise PlanningException(f"This is not a time-series predictor, aborting.")

    data_handler_table = getattr(query.from_table, data_side).parts[-1]
    data_handler_alias = getattr(query.from_table, data_side).alias
    data_handler_cols = list(set([t.parts[-1] for t in query.targets if t.parts[0] == str(data_handler_alias)]))

    window = model.problem_definition.timeseries_settings.window
    oby_col = model.problem_definition.timeseries_settings.order_by[0]
    gby_cols = model.problem_definition.timeseries_settings.group_by

    allowed_columns = [oby_col.lower()]
    if len(gby_cols) > 0:
        allowed_columns += [i.lower() for i in gby_cols]
    validate_ts_where_condition(query.where, allowed_columns=allowed_columns)

    time_filter = find_time_filter(query.where, time_column_name=oby_col)
    order_by = [OrderBy(Identifier(parts=[oby_col]), direction='DESC')]

    # step 2) get time filter
    preparation_where = copy.deepcopy(query.where)
    preparation_where = add_order_not_null(preparation_where, time_column_name=oby_col)
    time_selects = get_time_selects(time_filter, data_handler_table, window, order_by, preparation_where)

    # step 3) execute time filter on all required partitions
    if len(gby_cols) == 0:
        # no groups - one or multistep
        if len(time_selects) == 1:
            model_input = pd.DataFrame.from_records(data_handler.query(time_selects[0])['data_frame'])
        else:
            dfs = []
            for step in time_selects:
                dfs.append(pd.DataFrame.from_records(data_handler.query(step)['data_frame']))  # TODO: is this efficient if we have a double cutoff?
            model_input = pd.concat(dfs)
    else:
        # grouped
        groups = {}
        dfs = []
        # latests = {}
        # windows = {}
        for gcol in gby_cols:
            groups_query = Select(
                targets=[Identifier(gcol)],
                distinct=True,
                from_table=Identifier(data_handler_table),
            )
            groups[gcol] = list(data_handler.query(groups_query)['data_frame'].squeeze().values)

        partition_keys = list(groups.keys())
        all_partitions = list(product(*[v for k, v in groups.items()]))  # TODO: check, also whether there is a better way to maybe retrive then project?

        for group in all_partitions:
            group_time_selects = copy.deepcopy(time_selects)

            # TODO: pending
            # # one or multistep
            # if len(group_time_selects) == 1:
            #     partial_df = partial_dfs[0]
            # else:
            #     partial_df = pd.concat(partial_dfs)  # todo: check
            #
            # # get grouping values
            # # TODO: this time filter removal also sounds like we need to keep
            # no_time_filter_query = copy.deepcopy(query)
            # no_time_filter_query.where = find_and_remove_time_filter(no_time_filter_query.where, time_filter)
            # /TODO: pending

            filters = None
            for i, val in enumerate(group):
                col = partition_keys[i]
                binop = BinaryOperation(op='=',
                                        args=[
                                            Identifier(col),
                                            Constant(val)
                                        ])
                if filters is None:
                    filters = binop
                else:
                    filters = BinaryOperation(op='and', args=[filters, binop])

            # latest_oby_query = Select(  # TODO: don't think we need this one? check logic in time_selects...
            #     targets=[Identifier(oby_col)],
            #     from_table=Identifier(data_handler_table),
            #     where=filters,
            #     order_by=[OrderBy(
            #         field=Identifier(oby_col),
            #         direction='DESC'
            #     )],
            #     limit=Constant(1)
            # )
            # latests[group] = data_handler.query(latest_oby_query)['data_frame'].values[0][0]
            #
            # window_query = Select(
            #     targets=[Identifier(col) for col in data_handler_cols],
            #     from_table=Identifier(data_handler_table),
            #     where=BinaryOperation(op='=',
            #                           args=[
            #                               Identifier(gby_cols),
            #                               Constant(group)
            #                           ]),
            # )

            for time_select in group_time_selects:
                # TODO: pretty sure this doesn't cover intersection case...
                time_select.where = BinaryOperation(op='and', args=[time_select.where, filters])

                df = data_handler.query(time_select)['data_frame']
                # df = df.sort_values(oby_col, ascending=False).iloc[0:window] # TODO: may want to order and limit the df instead of SELECT to hedge against badly defined dtypes in the DB?
                dfs.append(df)

            # windows[group] = df[::-1]  # reorder to ASC

        # 3) concatenate all contexts into single data query
        model_input = pd.concat(dfs).reset_index(drop=True)

    return model_input