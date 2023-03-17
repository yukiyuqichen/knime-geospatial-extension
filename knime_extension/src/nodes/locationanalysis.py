import geopandas as gp
import knime_extension as knext
import util.knime_utils as knut


# import pickle
# from io import StringIO
# import sys

__category = knext.category(
    path="/community/geo",
    level_id="LocationAnalysis",
    name="Location Analysis",
    description="Location Analysis",
    # starting at the root folder of the extension_module parameter in the knime.yml file
    icon="icons/icon/LocationAnalysisCategory.png",
    after="spatialmodels",
)

# Root path for all node icons in this file
__NODE_ICON_PATH = "icons/icon/LocationAnalysis/"

############################################
# Location-allocation Pmedian
############################################
@knext.node(
    name="P-median",
    node_type=knext.NodeType.MANIPULATOR,
    icon_path=__NODE_ICON_PATH + "pmedian.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input OD list with geometries ",
    description="Table with geometry information of demand and supply ",
)
@knext.output_table(
    name="Demand table with P-median result",
    description="Demand table with assigned supply point and link",
)
@knut.pulp_node_description(
    short_description="Solve P-median problem minimize total weighted spatial costs.",
    description="The p-median model, one of the most widely used location models of any kind,"
    + "locates p facilities and allocates demand nodes to them to minimize total weighted distance traveled. "
    + "The P-Median problem will be solved by PuLP package. ",
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class PmedianNode:

    DemandID = knext.ColumnParameter(
        "Serial id column for demand",
        "Integer id number starting with 0",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyID = knext.ColumnParameter(
        "Serial id column for supply",
        "Integer id number starting with 0",
        # port_index=1,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    DemandPopu = knext.ColumnParameter(
        "Column for demand population",
        "The population of demand",
        # port_index=2,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    DemandGeometry = knext.ColumnParameter(
        "Geometry column for demand points",
        "The Geometry column for demand points",
        # port_index=3,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyGeometry = knext.ColumnParameter(
        "Geometry column for supply points",
        "The Geometry column for supply points",
        # port_index=4,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )
    ODcost = knext.ColumnParameter(
        "Travel cost between supply and demand",
        "The travel cost between the points of supply and demand",
        # port_index=5,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )
    # CRSinfo = knext.StringParameter(
    #     "Input CRSinfo for geometries of demand and supply",
    #     "The CRS information for geometry columns",
    #     "epsg:3857",
    # )
    Pnumber = knext.IntParameter(
        "Input optimum p number of p-median", "The optimum p number of p-median", 5
    )

    def configure(self, configure_context, input_schema_1):
        # knut.geo_column_exists(self.geo_col, input_schema_1)
        # TODO Create combined schema
        return None
        # knext.Schema.from_columns(
        # [
        #     knext.Column(knext.(), self.DemandID),
        #     knext.Column(knext.double(), self.DemandPopu),
        #     knext.Column(knext.double(), "geometry"),
        #     knext.Column(knext.double(), "assignSID"),
        #     knext.Column(knext.double(), "SIDwkt"),
        #     knext.Column(knext.double(), "Linewkt"),
        # ])

    def execute(self, exec_context: knext.ExecutionContext, input_1):
        df = gp.GeoDataFrame(input_1.to_pandas(), geometry=self.DemandGeometry)
        # Sort with DID and SID
        df = df.sort_values(by=[self.DemandID, self.SupplyID]).reset_index(drop=True)

        # rebuild demand and supply data
        DemandPt = (
            df[[self.DemandID, self.DemandPopu, self.DemandGeometry]]
            .groupby([self.DemandID])
            .first()
            .reset_index()
            .rename(columns={"index": self.DemandID, self.DemandGeometry: "geometry"})
        )
        SupplyPt = (
            df[[self.SupplyID, self.SupplyGeometry]]
            .groupby([self.SupplyID])
            .first()
            .reset_index()
            .rename(columns={"index": self.SupplyID, self.SupplyGeometry: "geometry"})
        )
        DemandPt = gp.GeoDataFrame(DemandPt, geometry="geometry")
        SupplyPt = gp.GeoDataFrame(SupplyPt, geometry="geometry")
        DemandPt = DemandPt.set_crs(df.crs)
        SupplyPt = SupplyPt.set_crs(df.crs)

        # calculate parameter for matrix
        num_trt = DemandPt.shape[0]
        num_hosp = SupplyPt.shape[0]

        import pulp

        # define problem
        problem = pulp.LpProblem("pmedian", sense=pulp.LpMinimize)

        def getIndex(s):
            li = s.split()
            if len(li) == 2:
                return int(li[-1])
            else:
                return int(li[-2]), int(li[-1])

        X = [
            "X" + " " + str(i) + " " + str(j)
            for i in range(num_trt)
            for j in range(num_hosp)
        ]
        Y = ["Y" + " " + str(j) for j in range(num_hosp)]

        varX = pulp.LpVariable.dicts("x", X, cat="Binary")
        varY = pulp.LpVariable.dicts("y", Y, cat="Binary")

        object_list = []
        for it in X:
            i, j = getIndex(it)
            cost = df[(df[self.DemandID] == i) & (df[self.SupplyID] == j)][
                self.ODcost
            ].values[0]
            object_list.append(DemandPt[self.DemandPopu][i] * cost * varX[it])
        problem += pulp.lpSum(object_list)

        problem += pulp.lpSum([varY[it] for it in Y]) == self.Pnumber
        for i in range(num_trt):
            problem += (
                pulp.lpSum(
                    [varX["X" + " " + str(i) + " " + str(j)] for j in range(num_hosp)]
                )
                == 1
            )
        for i in range(num_trt):
            for j in range(num_hosp):
                problem += (
                    varX["X" + " " + str(i) + " " + str(j)] - varY["Y" + " " + str(j)]
                    <= 0
                )

        problem.solve()
        print(pulp.LpStatus[problem.status])

        # Extract result

        DemandPt["assignSID"] = None
        DemandPt["SIDcoord"] = None
        for it in X:
            v = varX[it]
            if v.varValue == 1:
                i, j = getIndex(it)
                DemandPt.at[i, "assignSID"] = SupplyPt.at[j, self.SupplyID]
                DemandPt.at[i, "SIDcoord"] = SupplyPt.at[j, "geometry"]

        from shapely.geometry import LineString

        DemandPt["linxy"] = [
            LineString(xy) for xy in zip(DemandPt["geometry"], DemandPt["SIDcoord"])
        ]
        SIDwkt = gp.GeoDataFrame(geometry=DemandPt.SIDcoord, crs=df.crs)
        Linewkt = gp.GeoDataFrame(geometry=DemandPt.linxy, crs=df.crs)
        DemandPt["SIDwkt"] = SIDwkt.geometry
        DemandPt["Linewkt"] = Linewkt.geometry
        DemandPt = DemandPt.drop(columns=["linxy", "SIDcoord"])
        DemandPt = DemandPt.reset_index(drop=True)
        return knext.Table.from_pandas(DemandPt)


############################################
# Location-allocation LSCP
############################################
@knext.node(
    name="LSCP",
    node_type=knext.NodeType.MANIPULATOR,
    icon_path=__NODE_ICON_PATH + "LSCP.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input OD list with geometries ",
    description="Table with geometry information of demand and supply ",
)
@knext.output_table(
    name="Demand table with LSCP result",
    description="Demand table with assigned supply point and link",
)
@knut.pulp_node_description(
    short_description="Solve LSCP problem to minimize the number of facilities.",
    description="The LSCP problem,location set covering problem (LSCP), aims to cover all demand points within a threshold distance,"
    + "with minimizing the number of facilities. "
    + "The LSCP problem will be solved by PuLP package. ",
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class LSCPNode:

    DemandID = knext.ColumnParameter(
        "Serial id column for demand",
        "Integer id number starting with 0",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyID = knext.ColumnParameter(
        "Serial id column for supply",
        "Integer id number starting with 0",
        # port_index=1,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    DemandGeometry = knext.ColumnParameter(
        "Geometry column for demand points",
        "The Geometry column for demand points",
        # port_index=3,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyGeometry = knext.ColumnParameter(
        "Geometry column for supply points",
        "The Geometry column for supply points",
        # port_index=4,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )
    ODcost = knext.ColumnParameter(
        "Travel cost between supply and demand",
        "The travel cost between the points of supply and demand",
        # port_index=5,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )
    # CRSinfo = knext.StringParameter(
    #     "Input CRSinfo for geometries of demand and supply",
    #     "The CRS information for geometry columns",
    #     "epsg:3857",
    # )
    threshold = knext.DoubleParameter(
        "Input critical spatial cost", "Critical spatial cost to supply point", 13
    )

    def configure(self, configure_context, input_schema_1):
        # knut.geo_column_exists(self.geo_col, input_schema_1)
        # TODO Create combined schema
        return None
        # knext.Schema.from_columns(
        # [
        #     knext.Column(knext.(), self.DemandID),
        #     knext.Column(knext.double(), self.DemandPopu),
        #     knext.Column(knext.double(), "geometry"),
        #     knext.Column(knext.double(), "assignSID"),
        #     knext.Column(knext.double(), "SIDwkt"),
        #     knext.Column(knext.double(), "Linewkt"),
        # ])

    def execute(self, exec_context: knext.ExecutionContext, input_1):
        df = gp.GeoDataFrame(input_1.to_pandas(), geometry=self.DemandGeometry)
        # Sort with DID and SID
        df = df.sort_values(by=[self.DemandID, self.SupplyID]).reset_index(drop=True)

        # rebuild demand and supply data
        DemandPt = (
            df[[self.DemandID, self.DemandGeometry]]
            .groupby([self.DemandID])
            .first()
            .reset_index()
            .rename(columns={"index": self.DemandID, self.DemandGeometry: "geometry"})
        )
        SupplyPt = (
            df[[self.SupplyID, self.SupplyGeometry]]
            .groupby([self.SupplyID])
            .first()
            .reset_index()
            .rename(columns={"index": self.SupplyID, self.SupplyGeometry: "geometry"})
        )
        DemandPt = gp.GeoDataFrame(DemandPt, geometry="geometry")
        SupplyPt = gp.GeoDataFrame(SupplyPt, geometry="geometry")
        DemandPt = DemandPt.set_crs(df.crs)
        SupplyPt = SupplyPt.set_crs(df.crs)

        # calculate parameter for matrix
        num_trt = DemandPt.shape[0]
        num_hosp = SupplyPt.shape[0]

        df["within"] = 0
        df.loc[(df[self.ODcost] <= self.threshold), "within"] = 1

        import pulp

        # define problem
        problem = pulp.LpProblem("LSCPProblem", sense=pulp.LpMinimize)

        def getIndex(s):
            li = s.split()
            if len(li) == 2:
                return int(li[-1])
            else:
                return int(li[-2]), int(li[-1])

        X = ["X" + " " + str(j) for j in range(num_hosp)]
        varX = pulp.LpVariable.dicts("X", X, cat="Binary")

        object_list = []
        for it in X:
            object_list.append(varX[it])
        problem += pulp.lpSum(object_list)

        for i in range(num_trt):
            constrain = []
            for j in range(num_hosp):
                within = df[(df[self.DemandID] == i) & (df[self.SupplyID] == j)][
                    "within"
                ].values[0]
                constrain.append(within * varX["X" + " " + str(j)])
        problem += pulp.lpSum(constrain) >= 1

        problem.solve()
        # print(pulp.LpStatus[problem.status])

        DemandPt["assignSID"] = None
        DemandPt["SIDcoord"] = None

        import pandas as pd

        area = pd.DataFrame(columns=["OID"])
        for it in X:
            v = varX[it]
            if v.varValue == 1:
                print(1)
                j = getIndex(it)
                tempdict = {"OID": j}
                area = area.append(tempdict, ignore_index=True)

        for it in range(num_trt):
            index = pd.to_numeric(
                df[(df[self.DemandID] == it) & (df[self.SupplyID].isin(area["OID"]))][
                    self.ODcost
                ]
            ).idxmin()
            oid = int(df.at[index, self.SupplyID])
            DemandPt.at[it, "assignSID"] = SupplyPt.at[oid, self.SupplyID]
            DemandPt.at[it, "SIDcoord"] = SupplyPt.at[oid, "geometry"]

        from shapely.geometry import LineString

        DemandPt["linxy"] = [
            LineString(xy) for xy in zip(DemandPt["geometry"], DemandPt["SIDcoord"])
        ]
        SIDwkt = gp.GeoDataFrame(geometry=DemandPt.SIDcoord, crs=df.crs)
        Linewkt = gp.GeoDataFrame(geometry=DemandPt.linxy, crs=df.crs)
        DemandPt["SIDwkt"] = SIDwkt.geometry
        DemandPt["Linewkt"] = Linewkt.geometry
        DemandPt = DemandPt.drop(columns=["linxy", "SIDcoord"])
        DemandPt = DemandPt.reset_index(drop=True)
        return knext.Table.from_pandas(DemandPt)


############################################
# Location-allocation MCLP
############################################
@knext.node(
    name="MCLP",
    node_type=knext.NodeType.MANIPULATOR,
    icon_path=__NODE_ICON_PATH + "MCLP.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input OD list with geometries ",
    description="Table with geometry information of demand and supply",
)
@knext.output_table(
    name="Demand table with MCLP result",
    description="Demand table with assigned supply point and link",
)
@knut.pulp_node_description(
    short_description="Solve MCLP problem to Maximize Capacitated Coverage by setting an impedance cutoff.",
    description="The MCLP model, maximum covering location problem (MCLP), aims to Locate p facilities,"
    + " and demand is covered if it is within a specified distance (time) of a facility. "
    + "The P-Median problem will be solved by PuLP package. ",
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class MCLPNode:

    DemandID = knext.ColumnParameter(
        "Serial id column for demand",
        "Integer id number starting with 0",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyID = knext.ColumnParameter(
        "Serial id column for supply",
        "Integer id number starting with 0",
        # port_index=1,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    DemandPopu = knext.ColumnParameter(
        "Column for demand population",
        "The population of demand",
        # port_index=2,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    DemandGeometry = knext.ColumnParameter(
        "Geometry column for demand points",
        "The Geometry column for demand points",
        # port_index=3,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )

    SupplyGeometry = knext.ColumnParameter(
        "Geometry column for supply points",
        "The Geometry column for supply points",
        # port_index=4,
        column_filter=knut.is_geo,
        include_row_key=False,
        include_none_column=False,
    )
    ODcost = knext.ColumnParameter(
        "Travel cost between supply and demand",
        "The travel cost between the points of supply and demand",
        # port_index=5,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )
    # CRSinfo = knext.StringParameter(
    #     "Input CRSinfo for geometries of demand and supply",
    #     "The CRS information for geometry columns",
    #     "epsg:3857",
    # )
    Pnumber = knext.IntParameter(
        "Input optimum p number ", "The optimum p number of facilities", 3
    )
    threshold = knext.DoubleParameter(
        "Input critical spatial cost", "Critical spatial cost to supply point", 42000
    )

    def configure(self, configure_context, input_schema_1):
        # knut.geo_column_exists(self.geo_col, input_schema_1)
        # TODO Create combined schema
        return None
        # knext.Schema.from_columns(
        # [
        #     knext.Column(knext.(), self.DemandID),
        #     knext.Column(knext.double(), self.DemandPopu),
        #     knext.Column(knext.double(), "geometry"),
        #     knext.Column(knext.double(), "assignSID"),
        #     knext.Column(knext.double(), "SIDwkt"),
        #     knext.Column(knext.double(), "Linewkt"),
        # ])

    def execute(self, exec_context: knext.ExecutionContext, input_1):
        df = gp.GeoDataFrame(input_1.to_pandas(), geometry=self.DemandGeometry)
        # Sort with DID and SID
        df = df.sort_values(by=[self.DemandID, self.SupplyID]).reset_index(drop=True)

        # rebuild demand and supply data
        DemandPt = (
            df[[self.DemandID, self.DemandPopu, self.DemandGeometry]]
            .groupby([self.DemandID])
            .first()
            .reset_index()
            .rename(columns={"index": self.DemandID, self.DemandGeometry: "geometry"})
        )
        SupplyPt = (
            df[[self.SupplyID, self.SupplyGeometry]]
            .groupby([self.SupplyID])
            .first()
            .reset_index()
            .rename(columns={"index": self.SupplyID, self.SupplyGeometry: "geometry"})
        )
        DemandPt = gp.GeoDataFrame(DemandPt, geometry="geometry")
        SupplyPt = gp.GeoDataFrame(SupplyPt, geometry="geometry")
        DemandPt = DemandPt.set_crs(df.crs)
        SupplyPt = SupplyPt.set_crs(df.crs)

        # calculate parameter for matrix
        num_trt = DemandPt.shape[0]
        num_hosp = SupplyPt.shape[0]

        df["within"] = 0
        df.loc[(df[self.ODcost] <= self.threshold), "within"] = 1

        import pulp

        # define problem
        problem = pulp.LpProblem("MCLP", sense=pulp.LpMinimize)

        def getIndex(s):
            li = s.split()
            if len(li) == 2:
                return int(li[-1])
            else:
                return int(li[-2]), int(li[-1])

        X = ["X" + " " + str(j) for j in range(num_hosp)]
        Y = ["Y" + " " + str(i) for i in range(num_trt)]
        varX = pulp.LpVariable.dicts("assigned", X, cat="Binary")
        varY = pulp.LpVariable.dicts("covered", Y, cat="Binary")

        object_list = []
        for it in Y:
            i = getIndex(it)
            object_list.append(DemandPt[self.DemandPopu][i] * varY[it])
        problem += pulp.lpSum(object_list)

        problem += pulp.lpSum([varX[it] for it in X]) == self.Pnumber

        for i in range(num_trt):
            constrain = []
            for j in range(num_hosp):
                within = df[(df[self.DemandID] == i) & (df[self.SupplyID] == j)][
                    "within"
                ].values[0]
                constrain.append(within * varX["X" + " " + str(j)])
            constrain.append(varY["Y" + " " + str(i)])
            problem += pulp.lpSum(constrain) >= 1
        problem.solve()
        print(pulp.LpStatus[problem.status])

        DemandPt["assignSID"] = None
        DemandPt["SIDcoord"] = None

        import pandas as pd

        area = pd.DataFrame(columns=["OID"])
        for it in X:
            v = varX[it]
            if v.varValue == 1:
                j = getIndex(it)
                tempdict = {"OID": j}
                area = area.append(tempdict, ignore_index=True)

        for it in range(num_trt):
            index = pd.to_numeric(
                df[(df[self.DemandID] == it) & (df[self.SupplyID].isin(area["OID"]))][
                    self.ODcost
                ]
            ).idxmin()
            oid = int(df.at[index, self.SupplyID])
            DemandPt.at[it, "assignSID"] = SupplyPt.at[oid, self.SupplyID]
            DemandPt.at[it, "SIDcoord"] = SupplyPt.at[oid, "geometry"]

        from shapely.geometry import LineString

        DemandPt["linxy"] = [
            LineString(xy) for xy in zip(DemandPt["geometry"], DemandPt["SIDcoord"])
        ]
        SIDwkt = gp.GeoDataFrame(geometry=DemandPt.SIDcoord, crs=df.crs)
        Linewkt = gp.GeoDataFrame(geometry=DemandPt.linxy, crs=df.crs)
        DemandPt["SIDwkt"] = SIDwkt.geometry
        DemandPt["Linewkt"] = Linewkt.geometry
        DemandPt = DemandPt.drop(columns=["linxy", "SIDcoord"])
        DemandPt = DemandPt.reset_index(drop=True)
        return knext.Table.from_pandas(DemandPt)



############################################
# Location-allocation P-center Solver
############################################
@knext.node(
    name="P-center Solver",
    node_type=knext.NodeType.PREDICTOR,
    icon_path=__NODE_ICON_PATH + "pcenter.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input OD Matrix for candidate facilities (m rows X n columns )",
    description="Table with distance matrix to (n-1) candidate facilities and the nearest required facilities",
)
@knext.output_table(
    name="P-center result table",
    description="candidate column name and chosen status(1/0)",
)
@knut.pulp_node_description(
    short_description="p-center (minimax) Minimizes the maximum distance between demand points and their nearest facilities by locating p facilities.",
    description="""The p-center model help to chose p facliteis(p) from a set of  candidate facilities (n) for locations(m) based on the OD matrix (m X n). 
    If required facilities are considered, a column respresented the distance to the nearest required facilites should be specified.
    The p-center (minimax) problem will be solved by PuLP package. 
    """,
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class PcenterSolverNode:

    Pnumber = knext.IntParameter(
        "Input optimum p number ",
        "The optimum p number of facilities",
        3,
    )

    RequiredID = knext.ColumnParameter(
        "Column for required facility",
        "Travel cost column of  required facility or Travel cost column of nearest required facilities ",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=True,
    )

    def configure(self, configure_context, input_schema_1):
        return knext.Schema.from_columns(
            [
                knext.Column(knext.string(), "FacilityID"),
                knext.Column(knext.int32(), "Chosen"),
            ]
        )

    def execute(self, exec_context: knext.ExecutionContext, input_1):
        cost_matrix = gp.GeoDataFrame(input_1.to_pandas()).rename(
            columns={self.RequiredID: "Required"}
        )
        import pulp
        import pandas as pd

        P = self.Pnumber
        if self.RequiredID is not None:
            P = P + 1
        demand = cost_matrix.shape[0]
        candidate = cost_matrix.shape[1]
        # Whether exist required facilites
        if self.RequiredID is not None:
            last_col = cost_matrix["Required"]
            cost_matrix = pd.concat(
                [cost_matrix.drop(columns=["Required"]), last_col], axis=1
            )
            candidate = cost_matrix.shape[1]
            nrequire = candidate - 1

        # Define the optimization problem
        prob = pulp.LpProblem("p-center", pulp.LpMinimize)

        # Define the decision variables
        x = pulp.LpVariable.dicts(
            "x", [(i, j) for i in range(demand) for j in range(candidate)], cat="Binary"
        )
        y = pulp.LpVariable.dicts("y", [j for j in range(candidate)], cat="Binary")
        Z = pulp.LpVariable("Z", lowBound=0)

        # Define the objective function
        prob += Z

        # Define the constraints
        for i in range(demand):
            prob += pulp.lpSum([x[(i, j)] for j in range(candidate)]) == 1

        for j in range(candidate):
            for i in range(demand):
                prob += x[(i, j)] <= y[j]

        for i in range(demand):
            prob += (
                pulp.lpSum(
                    [x[(i, j)] * cost_matrix.iloc[i][j] for j in range(candidate)]
                )
                <= Z
            )

        prob += pulp.lpSum([y[j] for j in range(candidate)]) == P

        if self.RequiredID is not None:
            prob += y[nrequire] == 1

        # Solve the problem
        prob.solve()

        status = pulp.LpStatus[prob.status]
        print(f"Optimization status: {status}")
        # Extract the value of y for each candidate facility
        dfy = pd.DataFrame({"FacilityID": cost_matrix.columns})
        for j in range(candidate):
            dfy.loc[j, "Chosen"] = pulp.value(y[j])
        dfy["FacilityID"] = dfy["FacilityID"].astype(str)
        dfy["Chosen"] = dfy["Chosen"].astype(int)
        return knext.Table.from_pandas(dfy)


############################################
# Location-allocation P-median Solver
############################################
@knext.node(
    name="P-median Solver",
    node_type=knext.NodeType.PREDICTOR,
    icon_path=__NODE_ICON_PATH + "pmedian.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input demand data(m rows ) ",
    description="Table with demand column and distance column (optional) to the nearest required facilities ",
)
@knext.input_table(
    name="Input OD Matrix for candidate facilities (m rows X n columns )",
    description="Table with population and distance matrix to n candidate facilities, row order should be consistent with demand data and required",
)
@knext.output_table(
    name="P-median result table",
    description="candidate column name and chosen status(1/0)",
)
@knut.pulp_node_description(
    short_description="Solve P-median problem minimize total weighted spatial costs.",
    description="""The p-median model, one of the most widely used location models of any kind,
    locates p facilities and allocates demand nodes to them to minimize total weighted distance traveled. 
    If required facilities are considered, a column respresented the distance to the nearest required facilites should be specified.
    The P-Median problem will be solved by PuLP package. 
    """,
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class PmediaSolverNode:

    Pnumber = knext.IntParameter(
        "Input optimum p number of p-median ",
        "The optimum p number of p-median",
    )
    PopulationID = knext.ColumnParameter(
        "Demand column",
        "The column for demand (e.g., population) ",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    RequiredID = knext.ColumnParameter(
        "Distance column for required facilities",
        "The travel cost to the nearest required facilities ",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=True,
    )

    def configure(self, configure_context, input_schema_1, input_schema_2):
        return knext.Schema.from_columns(
            [
                knext.Column(knext.string(), "FacilityID"),
                knext.Column(knext.int32(), "Chosen"),
            ]
        )

    def execute(self, exec_context: knext.ExecutionContext, input_1, input_2):
        df1 = gp.GeoDataFrame(input_1.to_pandas()).rename(
            columns={self.RequiredID: "Required"}
        )
        df2 = gp.GeoDataFrame(input_2.to_pandas())
        import pulp
        import pandas as pd

        P = self.Pnumber
        if self.RequiredID is not None:
            P = P + 1
        popu = df1[self.PopulationID].values.tolist()
        cost_matrix = df2
        demand = cost_matrix.shape[0]
        candidate = cost_matrix.shape[1]
        # Whether exist required facilites
        if self.RequiredID is not None:
            last_col = df1["Required"]
            cost_matrix = pd.concat([cost_matrix, last_col], axis=1)
            candidate = cost_matrix.shape[1]
            nrequire = candidate - 1

        # Define the optimization problem
        prob = pulp.LpProblem("p-media", pulp.LpMinimize)

        # Define the decision variables
        x = pulp.LpVariable.dicts(
            "x", [(i, j) for i in range(demand) for j in range(candidate)], cat="Binary"
        )
        y = pulp.LpVariable.dicts("y", [j for j in range(candidate)], cat="Binary")

        # Define the objective function
        prob += pulp.lpSum(
            [
                x[(i, j)] * cost_matrix.iloc[i][j] * popu[i]
                for i in range(demand)
                for j in range(candidate)
            ]
        )

        # Define the constraints
        for i in range(demand):
            prob += pulp.lpSum([x[(i, j)] for j in range(candidate)]) == 1

        for j in range(candidate):
            for i in range(demand):
                prob += x[(i, j)] <= y[j]

        prob += pulp.lpSum([y[j] for j in range(candidate)]) == P

        if self.RequiredID is not None:
            prob += y[nrequire] == 1

        # Solve the problem
        prob.solve()

        status = pulp.LpStatus[prob.status]
        print(f"Optimization status: {status}")

        # Extract the value of y for each candidate facility
        dfy = pd.DataFrame({"FacilityID": cost_matrix.columns})
        for j in range(candidate):
            dfy.loc[j, "Chosen"] = pulp.value(y[j])
        dfy["FacilityID"] = dfy["FacilityID"].astype(str)
        dfy["Chosen"] = dfy["Chosen"].astype(int)
        return knext.Table.from_pandas(dfy)


############################################
# Location-allocation MCLP Solver
############################################
@knext.node(
    name="MCLP Solver",
    node_type=knext.NodeType.PREDICTOR,
    icon_path=__NODE_ICON_PATH + "MCLP.png",
    category=__category,
    after="",
)
@knext.input_table(
    name="Input demand data(m rows ) ",
    description="Table with demand column and distance column (optional) to the nearest required facilities ",
)
@knext.input_table(
    name="Input OD Matrix for candidate facilities (m rows X n columns )",
    description="Table with population and distance matrix to n candidate facilities, row order should be consistent with demand data and required",
)
@knext.output_table(
    name="P-median result table",
    description="candidate column name and chosen status(1/0)",
)
@knut.pulp_node_description(
    short_description="Solve MCLP problem to Maximize Capacitated Coverage by setting an impedance cutoff.",
    description="""The MCLP model, maximum covering location problem (MCLP), aims to Locate p facilities,
    and demand is covered if it is within a specified distance (time) of a facility. 
    If required facilities are considered, a column respresented the distance to the nearest required facilites should be specified.
    The P-Median problem will be solved by PuLP package. 
    """,
    references={
        "Pulp.Solver": "https://coin-or.github.io/pulp/guides/how_to_configure_solvers.html",
    },
)
class MCLPSolverNode:

    Pnumber = knext.IntParameter(
        "Optimum p number ",
        "The optimum p number of facilities",
        4,
    )
    Threshold = knext.DoubleParameter(
        "Threshold",
        "Desired threshold distance or cost",
    )
    PopulationID = knext.ColumnParameter(
        "Demand column",
        "The column for demand (e.g., population) ",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=False,
    )

    RequiredID = knext.ColumnParameter(
        "Distance column for required facilities",
        "The travel cost to the nearest required facilities ",
        # port_index=0,
        column_filter=knut.is_numeric,
        include_row_key=False,
        include_none_column=True,
    )

    def configure(self, configure_context, input_schema_1, input_schema_2):
        return knext.Schema.from_columns(
            [
                knext.Column(knext.string(), "FacilityID"),
                knext.Column(knext.int32(), "Chosen"),
            ]
        )

    def execute(self, exec_context: knext.ExecutionContext, input_1, input_2):
        df1 = gp.GeoDataFrame(input_1.to_pandas()).rename(
            columns={self.RequiredID: "Required"}
        )
        df2 = gp.GeoDataFrame(input_2.to_pandas())
        import pulp
        import pandas as pd

        P = self.Pnumber
        if self.RequiredID is not None:
            P = P + 1
        popu = df1[self.PopulationID].values.tolist()
        cost_matrix = df2
        demand = cost_matrix.shape[0]
        candidate = cost_matrix.shape[1]
        cutoff = self.Threshold
        # Whether exist required facilites
        if self.RequiredID is not None:
            last_col = df1["Required"]
            cost_matrix = pd.concat([cost_matrix, last_col], axis=1)
            candidate = cost_matrix.shape[1]
            nrequire = candidate - 1

        # Define the optimization problem
        prob = pulp.LpProblem("mclp", pulp.LpMinimize)

        # Define the decision variables
        x = pulp.LpVariable.dicts(
            "x", [(i, j) for i in range(demand) for j in range(candidate)], cat="Binary"
        )
        y = pulp.LpVariable.dicts("y", [j for j in range(candidate)], cat="Binary")

        # Define the objective function

        prob += pulp.lpSum(
            [x[(i, j)] * popu[i] for i in range(demand) for j in range(candidate)]
        )

        # Define the constraints
        for i in range(demand):
            prob += pulp.lpSum([x[(i, j)] for j in range(candidate)]) == 1

        for j in range(candidate):
            for i in range(demand):
                prob += x[(i, j)] <= y[j]

        # Define the threshold cutoff distance constraint
        for i in range(demand):
            prob += (
                pulp.lpSum(
                    [cost_matrix.iloc[i][j] * x[(i, j)] for j in range(candidate)]
                )
                <= cutoff
            )

        # Define the one facility required constraint
        prob += pulp.lpSum([y[j] for j in range(candidate)]) == P
        prob += y[nrequire] == 1
        # Solve the problem
        prob.solve()

        status = pulp.LpStatus[prob.status]
        print(f"Optimization status: {status}")

        # Extract the value of y for each candidate facility
        dfy = pd.DataFrame({"FacilityID": cost_matrix.columns})
        for j in range(candidate):
            dfy.loc[j, "Chosen"] = pulp.value(y[j])
        dfy["FacilityID"] = dfy["FacilityID"].astype(str)
        dfy["Chosen"] = dfy["Chosen"].astype(int)
        return knext.Table.from_pandas(dfy)